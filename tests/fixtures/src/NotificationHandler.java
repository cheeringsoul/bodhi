package com.example.notification;

public class NotificationHandler {

    /**
     * @bodhi.intent 收到订单创建事件后，发送通知给用户
     * @bodhi.consumes order_created(orderId, userId) from kafka:order-events
     * @bodhi.reads users(email) WHERE id = userId
     * @bodhi.calls EmailService.send
     * @bodhi.on_fail email_send_failed → retry 3 → alert ops
     */
    public void onOrderCreated(OrderCreatedEvent event) {
        // ...
    }

    /**
     * @bodhi.intent 收到支付完成事件后，更新通知状态
     * @bodhi.consumes payment_completed(orderId, transactionId) from kafka:payment-events
     * @bodhi.writes notifications(orderId, status=SENT) via UPDATE
     */
    public void onPaymentCompleted(PaymentCompletedEvent event) {
        // ...
    }
}
