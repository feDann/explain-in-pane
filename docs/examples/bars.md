# Memory against the limit

## 1. A rebalance pushes the pod over its limit

```bars cap=1024 unit=MiB
steady: heap 420, batch 260, meta 140
rebalance: heap 420, batch 260, old batch 260 orange, meta 140
rebalance, fix: heap 420, batch 104, old batch 104 orange, meta 140
```
