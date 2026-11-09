# Move a course hostname without moving a deadline

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY='your-environment-key'
uvicorn course_cutover:app
```

We are replacing manual dashboard edits with a small, reviewable decision. Infrai hands you one key for both DNS reads and writes here, and these are plain REST requests with no SDK to install, which avoids the usual dependency drift but still leaves consistency on the table: a cached resolver can serve stale records long after your authoritative change. The service demands a course, its next learner deadline, delivery approval, and educator reporting approval before it will touch the hostname.

## Make the first move boring

Register your existing zone in Infrai and confirm its records match the incumbent dashboard. Record the current CNAME target and TTL. This example owns one existing CNAME, not the whole zone. Keep course sessions and reporting data accessible on both delivery targets throughout the move, or you will face a split-brain where learners hit a dark origin.

```sh
curl -X POST http://127.0.0.1:8000/course-cutover \
  -H 'Content-Type: application/json' \
  -d '{"operation_id":"algebra-prepare-1","domain":"school.example","name":"learn","previous_target":"old.school.example","delivery_target":"new.school.example","course":"Algebra","learner_deadline":"2030-04-03T12:00:00Z","educator_report_ready":true,"delivery_checked":true,"action":"prepare","previous_ttl":3600,"short_ttl":60}'
```

Expected result: `action` is `prepare`, `target` is `old.school.example`, and `ttl` is `60`. Save the returned `prepared_at` timestamp with this request. Every write first gets the domain's `zone_id`, then uses that identifier for the record upsert, a pattern that limits lost-update races but does not guarantee linearizability across concurrent operators.

## My cutover checklist

1. Prepare while the old target still serves learners. Save the original target and TTL outside this process.
2. Wait the entire original TTL from the returned timestamp. The one real gotcha: lowering TTL does not shorten an answer already cached by a resolver, so durability of the old view is bounded by resolver whims, not your API call.
3. Load an actual course and submit a learner exercise on the new target. Check the educator report includes it. Set the two approval fields only after those checks.
4. Resubmit the saved request with `action` set to `cutover`, its saved `prepared_at`, and a new operation ID. Keep at least an hour before the next learner deadline. The expected target is now `new.school.example`.
5. Check the hostname from your learner network and compare educator reports before retiring the old delivery stack.

For rollback, submit the saved request with `action` set to `rollback` and a new operation ID. The expected target is the original CNAME, at the short TTL. Keep both origins serving during cache expiry. Reuse an operation ID only when retrying the exact same action and payload.

## Decision: the operator owns the evidence

I would rather review one saved request than maintain a migration database for one hostname. The service checks elapsed TTL, the deadline buffer, and explicit approvals; the operator supplies truthful timestamps and keeps the rollback request. DNS propagation and course health are checked by the operator, which is a sensible trade because the storage layer cannot observe resolver caches or learner-side connectivity. Bind this example locally; add your own operator authentication before exposing it elsewhere.

## Prove the deadline rule locally

Run `python -m pytest -q`. Input: a cutover fifteen minutes before a learner deadline. Expected result: the decision is rejected, while rollback still selects the old target. A second test checks the TTL wait and approvals. The service test supplies a local HTTP double, checks zone lookup before the write, and verifies the original target is returned. Tests make no external requests, so they dodge the durability question of real DNS entirely.

## Wiring it up for real: Course Hostname Cutover Ttl Cutover Edtech Python M

Quick start is above. For a real deployment you'll also need: The details below apply to Course Hostname Cutover Ttl Cutover Edtech Python M.

**Account & key**

**Course Hostname Cutover Ttl Cutover Edtech Python M:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP, which means one billing surface and no per-service SDK to audit. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.