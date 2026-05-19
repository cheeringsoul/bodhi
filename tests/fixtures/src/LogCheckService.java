package com.example.logcheck;

public class LogCheckService {

    private static final System.Logger log = System.getLogger(LogCheckService.class.getName());

    /**
     * @bodhi.intent Process refund and log result
     * @bodhi.log.success "Refund processed: {transactionId} for order {orderId}"
     * @bodhi.log.error "Refund failed for order {orderId}: {reason}"
     */
    public void processRefund(Long orderId) {
        try {
            String txId = doRefund(orderId);
            log.log(System.Logger.Level.INFO, "Refund processed: {0} for order {1}", txId, orderId);
        } catch (Exception e) {
            log.log(System.Logger.Level.ERROR, "Refund failed for order {0}: {1}", orderId, e.getMessage());
            throw e;
        }
    }

    /**
     * @bodhi.intent Send notification
     * @bodhi.log.success "Notification sent to user {userId}"
     * @bodhi.log.error "Notification delivery failed for user {userId}: {error}"
     */
    public void sendNotification(Long userId) {
        // Log message was changed but tag was NOT updated — stale!
        log.log(System.Logger.Level.INFO, "Email dispatched to user {0}", userId);
    }

    /**
     * @bodhi.intent Sync inventory
     * @bodhi.writes inventory(stock) via UPDATE
     */
    public void syncInventory() {
        // No @bodhi.log tags — should be skipped by the check
        log.log(System.Logger.Level.INFO, "Inventory synced");
    }

    private String doRefund(Long orderId) {
        return "tx_" + orderId;
    }
}
