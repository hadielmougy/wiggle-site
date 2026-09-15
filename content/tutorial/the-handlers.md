# The handlers

The topology names steps. This is the code that runs them — a plain class, no framework base type,
no annotations per method.

<!-- snippet: tutorial-handlers/handlers -->
```java
@ForFlow("orders")                                  // which flow these steps belong to
public class OrderHandlers implements OrderSteps {  // implementing the contract is optional,
                                                    // but then the compiler checks every signature

    @Override public Order validate(Order o) {
        if (o.items().isEmpty()) throw new IllegalArgumentException("empty order " + o.id());
        return o.withStatus("VALIDATED");
    }

    @Override public boolean inStock(Order o) {
        return o.items().size() <= 50;              // false ends the instance cleanly, not as a failure
    }

    @Override public Item price(Item item) {
        return new Item(item.sku(), item.price().multiply(new BigDecimal("1.20")));   // + VAT
    }

    @Override public Order total(@Context Order base, List<Item> priced) {
        return base.withTotal(priced.stream().map(Item::price)
                .reduce(BigDecimal.ZERO, BigDecimal::add));
    }

    @Override public Order confirm(Order o) {
        return o.withStatus("CONFIRMED");
    }
}
```

## How a method becomes a step

`@ForFlow("orders")` says which flow the class serves. Within it, **binding is by method name**:
`validate` serves the step named `validate`. Names are folded canonically, so a step named
`in-stock` and a method called `inStock` are the same thing. When a method name cannot match — a
clash with something else, or a name you don't control — annotate it with `@Handles("step-name")`.

`implements OrderSteps` is optional: the worker binds by name and signature either way. Do it
anyway. It costs nothing and turns "this handler doesn't match the contract" from a startup error
into a compile error, which is the difference between finding out now and finding out at 3am. Note
that `@Context` has to be repeated on the implementation — parameter annotations are not inherited,
and the binder reads the method that actually runs.

## Throwing, and what happens next

`validate` throws on an empty order. That is the normal way to fail a step: the engine catches it,
applies the step's retry policy, and if the attempts run out the instance lands `FAILED` with the
error attached. Nothing is lost — a failed instance is resumable.

Compare that with `inStock` returning `false`, which is not a failure at all. Choosing correctly
between the two is most of what makes a flow pleasant to operate: alarms should mean something.

Next: **[run it](/tutorial/run-it/)**.
