# Rebalance memory

## 1. A rebalance makes the pod hold two batches

```flow
kafka (topic: webhooks) -->|poll 500| consumer (1 pod, 1024 MiB) -->|insert| postgres
consumer -->|rebalance before commit| {orange: old batch (not committed)}
```

{orange: Two batches sit in memory at once}: the new poll and the one the rebalance left
uncommitted.

## 2. Memory against the 1024 MiB limit

```bars cap=1024 unit=MiB
steady: heap 420, batch 260, meta 140
rebalance: heap 420, batch 260, old batch 260 orange, meta 140
rebalance, fix: heap 420, batch 104, old batch 104 orange, meta 140
```

## 3. What to change

| Change | Effect | Verdict |
|---|---|---|
| `max.poll.records` 500 -> 200 | both batches shrink to 104 MiB | {green: Keep.} |
| commit in `onPartitionsRevoked` | the old batch is freed at once | {green: Keep.} |
| limit 1024 -> 1536 MiB | hides it until the next spike | {red: Cut} |
| more replicas | each pod still holds two batches | {red: Cut} |

> Only the kept changes lower the peak itself.

# Why a 401 becomes a 500

## 1. The call path

```seq
client -> api: POST /charge
api -> billing: authorize
billing -> {red: gateway}: create payment
gateway --> billing: {red: 401, code 34}
note billing: no mapping for code 34, so it throws GatewayError
billing --> api: {red: 500}
api --> client: {red: 500}
--- the client retries, up to 10 times ---
client -> client: back off
```

## 2. Before and after the mapping

::: panels
### {red: before}
- code 34 is in neither list
- authorize answers **500**
- the client retries the charge 10 times

### {green: after}
- code 34 maps to `DECLINED`
- authorize answers a decline
- the client stops at the first answer
:::

## 3. Retries go back through the queue

```flow
client -->|POST /pay| api -->|enqueue| queue -->|deliver| worker
worker -->|{red: 503, retry}| queue
```

1. The worker answers 503 when the gateway is down.
2. The message goes back to the queue with a delay.

---

```text
retry.delay = 30s * 2^attempt
```

# A tree

## 1. Why urllib3 is in the build

```tree depth=3
app (python 3.12)
  requests 2.31
    urllib3 2.0
    certifi
  {red: pygments 2.16}
  urllib3 2.0 (*)
```

## 2. An AST, each field on its edge

```tree
Assign
  target: Name (x)
  value: BinOp (+)
    left: Constant (2)
    right: BinOp (*)
      left: Name (y)
      right: Constant (3)
```
