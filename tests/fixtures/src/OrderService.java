package com.example.order;

public class OrderService {

    /**
     * @bodhi.intent 创建订单，扣减库存，发布领域事件
     * @bodhi.reads request.body(userId, items, address)
     * @bodhi.writes orders(id, userId, totalAmount, status=PENDING) via INSERT
     * @bodhi.calls InventoryService.deduct, PaymentService.hold
     * @bodhi.emits order_created(orderId, userId) to kafka:order-events
     * @bodhi.on_fail inventory_insufficient → reject 400
     * @bodhi.on_fail payment_timeout → retry 3 → reject 500
     */
    public OrderResponse create(CreateOrderRequest req) {
        // ...
    }

    /**
     * @bodhi.intent 取消订单，回滚库存
     * @bodhi.reads orders(id, status) WHERE id = orderId
     * @bodhi.writes orders(status=CANCELLED) via UPDATE
     * @bodhi.calls InventoryService.rollback
     * @bodhi.emits order_cancelled(orderId) to kafka:order-events
     * @bodhi.on_fail order_not_found → reject 404
     */
    public void cancel(Long orderId) {
        // ...
    }

    /**
     * @bodhi.writes audit_log(action, orderId) via INSERT
     */
    public void logAction(String action, Long orderId) {
        // missing intent — should trigger validation error
    }

    public String getName() {
        // no bodhi tags — getter, should be skipped
        return "order";
    }
}
