package com.example.order;

// Fixture for method-overloading validator rule:
// two tagged methods share the same ClassName.methodName identifier.
public class BatchProcessor {

    /**
     * @bodhi.intent Process a single order
     * @bodhi.reads orders(id, status)
     * @bodhi.writes orders(status) via UPDATE
     */
    public void process(Order order) {
        // ...
    }

    /**
     * @bodhi.intent Process a batch of orders
     * @bodhi.reads orders(id, status)
     * @bodhi.writes orders(status) via UPDATE
     */
    public void process(BatchOrder batch) {
        // ...
    }
}
