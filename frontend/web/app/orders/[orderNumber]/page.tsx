export default async function OrderDetail({ params }: { params: Promise<{ orderNumber: string }> }) { const { orderNumber } = await params; return <section><h1>Order {orderNumber}</h1><p>Your timeline will appear here after authentication is connected to the order API.</p><ol><li>Order placed</li><li>Pickup scheduled</li><li>At alteration partner</li><li>Ready for delivery</li></ol></section>; }

