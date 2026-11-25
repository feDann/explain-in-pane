# Dependencies

## 1. Why urllib3 is in the build

```tree depth=3
app
  requests 2.31
    urllib3 2.0
    certifi
  rich 13.7
    pygments
  urllib3 2.0 (*)
```

{cyan: urllib3 comes in twice}: through requests, and straight from the app.

## 2. An AST, with its fields

```tree
Assign
  target: Name (x)
  value: BinOp (+)
    left: Constant (2)
    right: BinOp (*)
      left: Name (y)
      right: Constant (3)
```
