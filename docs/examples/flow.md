# Retry flow

## 1. A failed delivery goes back through the queue

```flow
client -->|POST /pay| api -->|enqueue| queue -->|deliver| worker
worker -->|{red: 503, retry}| queue
```

The worker answers {red: 503} while the gateway is down, and the message returns after a delay.
