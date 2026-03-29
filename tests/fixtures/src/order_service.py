class OrderService:

    def create_order(self, req):
        """
        @bodhi.intent 创建订单
        @bodhi.reads request.body(userId, items)
        @bodhi.writes orders(id, userId, status=PENDING) via INSERT
        @bodhi.calls PaymentService.charge
        """
        pass

    def get_order(self, order_id):
        """
        @bodhi.intent 查询订单详情
        @bodhi.reads orders(id, userId, status, totalAmount) WHERE id = order_id
        """
        pass
