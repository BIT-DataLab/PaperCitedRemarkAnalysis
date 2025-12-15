已知当前 @ref_code/get_reference_ctx/get_paper_ref_context.py脚本提取出的pdf文本中的References前面可能会携带额外的格式符，比如markdown层级标识符和加粗符。

我需要你修改当前的引用识别demo代码 @ref_code/get_reference_ctx/get_paper_ref_context.py 中的逻辑，让它能识别各种形式的引用出现情况(References/Bibliography)
比如下面这些类型
```
References
References
**References** 
## **References** 
```

注意匹配的时候应该是单行出现的，如果那一行的自然语言文本还有除了References 之外的其他内容，就不应该被识别为References标题行。