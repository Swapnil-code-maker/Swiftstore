def calculate_vendor_payout(order_item):
    gross = order_item.price_at_purchase * order_item.quantity

    commission = gross * order_item.commission_rate

    pg_rate = 0.02
    pg_fee = gross * pg_rate

    net = gross - commission - pg_fee

    return {
        "gross": gross,
        "commission": commission,
        "pg_fee": pg_fee,
        "net": net
    }
