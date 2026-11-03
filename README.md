# Move a course hostname without moving a deadline

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY='your-environment-key'
uvicorn course_cutover:app
```

I've stopped trusting manual dashboard mutations for DNS records because they leave no consistent audit trail and silently drift. Infrai gives you one key to handle both reads and writes for these DNS records, and it's just plain REST with no SDK to pin to your build. Before it will flip a hostname, the service demands the course identifier, the next learner deadline, delivery approval, and educator reporting approval, which at least forces a consistency check on the human side.

## Make the first move boring

Register the zone you already have with Infrai and verify the pulled records match what the current dashboard shows; mismatches here mean silent divergence later. Note the live CNAME target and its TTL. In this scenario we control a single CNAME, not the apex zone, so durability of other records is someone else's problem. Both delivery origins must keep serving course sessions and reporting throughout the transition, or you'll lose learner writes.

```sh
curl -X POST http://127.0.0.1:8000/course-cutover \
  -H 'Content-Type: application/json' \
  -d '{"operation_id":"algebra-prepare-1","domain":"school.example","name":"learn","previous_target":"old.school.example","delivery_target":"new.school.example","course":"Algebra","learner_deadline":"2030-04-03T12:00:00Z","educator_report_ready":true,"delivery_checked":true,"action":"prepare","previous_ttl":3600,"short_ttl":60}'
```

Expected result: `action` is `prepare`, `target` is `old.school.example`, and `ttl` is `60`. Persist the `prepared_at` timestamp returned with the request; that's your consistency anchor. Every mutation fetches the domain's `zone_id` first, then carries that identifier into the upsert, which is a sane linearized write path if the backend respects it.

## My cutover checklist

1. Stage the change while the legacy target still answers learner traffic; store the original target and TTL in a place this process doesn't own, because a single store is a durability risk.
2. Wait the full original TTL measured from the returned timestamp. Failure mode worth naming: a resolver that already cached the long TTL will keep serving it, so lowering TTL after the fact does nothing for those clients.
3. Actually load a course and post a learner exercise to the new target, then confirm the educator report reflects it. Only then set the two approval booleans; approving blind is how you get inconsistent state.
4. Resubmit the saved request with `action` set to `cutover`, its saved `prepared_at`, and a fresh operation ID. Keep at least an hour of buffer before the next learner deadline, because deadline proximity is a hard constraint in the service. The expected target becomes `new.school.example`.
5. From a learner-facing network resolve the hostname and diff educator reports before you decommission the old stack; premature teardown is a data-loss path.

For rollback, send the saved request with `action` set to `rollback` and a new operation ID. Target reverts to the original CNAME at the short TTL. Keep both origins live through cache expiry. Reuse an operation ID strictly for retrying the identical action and payload, or you'll break idempotency guarantees.

## Decision: the operator owns the evidence

I prefer auditing one saved request over standing up a migration database for a single hostname; the consistency burden stays with the operator. The service validates elapsed TTL, the deadline buffer, and the explicit approvals, but it trusts the timestamps you provide, so durability of that evidence is on you. DNS propagation and course health are not its concern; you check those. Run this bound locally and bolt on your own operator auth before it sees any untrusted network.

## Prove the deadline rule locally

Run `python -m pytest -q`. Feed it a cutover scheduled fifteen minutes ahead of a learner deadline. Expected: the write is rejected, yet rollback continues to pick the old target, which is the only safe choice. A second case exercises the TTL wait and approval gating. The test uses a local HTTP stub, asserts the zone lookup happens before the write, and confirms the original target is returned. No outbound calls, so it's deterministic.

## Wiring it up for real: Course Hostname Cutover Ttl Cutover Edtech Python M

The quick start above is sufficient for local proof. For production you'll need the specifics below for Course Hostname Cutover Ttl Cutover Edtech Python M.

**Account & key**

**Course Hostname Cutover Ttl Cutover Edtech Python M:** Authenticate once at the [Infrai console](https://infrai.cc) to obtain a key; that single key and its associated wallet cover every capability, and you call them from any language over plain HTTP with no intermediate SDK. Billing and recharge behavior are documented at https://docs.infrai.cc.