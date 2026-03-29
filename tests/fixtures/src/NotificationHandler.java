package com.example.notification;

public class NotificationHandler {

    /**
     * @bodhi.intent On order created event, send notification to user
     * @bodhi.consumes order_created(orderId, userId) from kafka:order-events
     * @bodhi.reads users(email) WHERE id = userId
     * @bodhi.calls EmailService.send
     * @bodhi.on_fail email_send_failed → retry 3 → alert ops
     */
    public void onOrderCreated(OrderCreatedEvent event) {
        // ...
    }

    /**
     * @bodhi.intent On payment completed event, update notification status
     * @bodhi.consumes payment_completed(orderId, transactionId) from kafka:payment-events
     * @bodhi.writes notifications(orderId, status=SENT) via UPDATE
     */
    public void onPaymentCompleted(PaymentCompletedEvent event) {
        // ...
    }
}
