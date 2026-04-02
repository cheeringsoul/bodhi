package com.example.payment;

public class PaymentService {

    /**
     * @bodhi.intent Hold payment for order
     * @bodhi.trace orderId
     * @bodhi.reads orders(id, totalAmount) WHERE id = orderId
     * @bodhi.log.success "Payment held: {transactionId} for order {orderId}"
     * @bodhi.log.error "Payment failed for order {orderId}: {reason}"
     */
    public PaymentResult hold(Long orderId, BigDecimal amount) {
        // ...
    }

    /**
     * @bodhi.intent Refund payment
     * @bodhi.log.success "Refund completed for transaction {transactionId}"
     * @bodhi.log.error "Refund failed for transaction {transactionId}: {reason}"
     */
    public void refund(String transactionId) {
        // ...
    }
}
