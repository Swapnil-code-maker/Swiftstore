let cart = JSON.parse(localStorage.getItem("swiftCart")) || [];


/* ---------------- ADD TO CART ---------------- */

function addToCartWithQty(id, name, price, vendorId) {

    const qty = parseInt(document.getElementById(`qty-${id}`).innerText);

    const existing = cart.find(item => item.id === id);

    if (existing) {
        existing.quantity += qty;
    } else {
        cart.push({
            id,
            name,
            price,
            vendor_id: vendorId,
            quantity: qty
        });
    }

    updateCartUI();
}


/* ---------------- UPDATE CART UI ---------------- */

function updateCartUI() {

    const cartCount = document.querySelector(".cart-count");
    const cartContent = document.querySelector(".cart-content");
    const cartBottom = document.querySelector(".cart-bottom");

    if (!cartCount || !cartContent || !cartBottom) return;

    let totalItems = 0;
    let subtotal = 0;

    cart.forEach(item => {
        totalItems += item.quantity;
        subtotal += item.price * item.quantity;
    });

    cartCount.textContent = totalItems;

    /* ---------------- EMPTY CART ---------------- */

    if (cart.length === 0) {
        cartContent.innerHTML = `
            <div class="empty-cart">
                <p>Your cart is empty</p>
                <small>Add items to get 10 min delivery</small>
            </div>
        `;
        cartBottom.innerHTML = "";
        return;
    }

    /* ---------------- CART ITEMS ---------------- */

    cartContent.innerHTML = cart.map(item => `
        <div class="cart-item">
            <div class="cart-info">
                <strong>${item.name}</strong>
                <div>₹${item.price} × ${item.quantity}</div>
            </div>

            <div class="cart-controls">
                <button onclick="changeCartQty(${item.id}, -1)">−</button>
                <span>${item.quantity}</span>
                <button onclick="changeCartQty(${item.id}, 1)">+</button>
                <button onclick="removeFromCart(${item.id})">🗑</button>
            </div>
        </div>
    `).join("");

    /* ---------------- BILLING ---------------- */

    let deliveryFee = subtotal > 199 ? 0 : 25;
    let platformFee = subtotal * 0.02;
    let total = subtotal + deliveryFee + platformFee;

    cartBottom.innerHTML = `
        <div class="billing-box">
            <div class="bill-row">
                <span>Items</span>
                <span>${totalItems}</span>
            </div>

            <div class="bill-row">
                <span>Subtotal</span>
                <span>₹${subtotal.toFixed(2)}</span>
            </div>

            <div class="bill-row">
                <span>Delivery Fee</span>
                <span>₹${deliveryFee.toFixed(2)}</span>
            </div>

            <div class="bill-row">
                <span>Platform Fee</span>
                <span>₹${platformFee.toFixed(2)}</span>
            </div>

            <hr>

            <div class="bill-total">
                <span>Total</span>
                <span>₹${total.toFixed(2)}</span>
            </div>

            <button class="checkout-btn" onclick="placeOrder()">
                Buy Now
            </button>
        </div>
    `;
    if (cart.length > 0) {
    localStorage.setItem("swiftCart", JSON.stringify(cart));
} else {
    localStorage.removeItem("swiftCart");
}


}


/* ---------------- CHANGE CART QTY ---------------- */

function changeCartQty(id, delta) {

    const item = cart.find(i => i.id === id);
    if (!item) return;

    item.quantity += delta;

    if (item.quantity <= 0) {
        cart = cart.filter(i => i.id !== id);
    }

    updateCartUI();
}


/* ---------------- REMOVE ITEM ---------------- */

function removeFromCart(id) {
    cart = cart.filter(item => item.id !== id);
    updateCartUI();
}


/* ---------------- PLACE ORDER ---------------- */

function placeOrder() {

    if (cart.length === 0) {
        alert("Cart is empty");
        return;
    }

    fetch("/create-order", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            items: cart.map(item => ({
                product_id: item.id,
                quantity: item.quantity
            }))
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {

    // 1️⃣ Clear JS cart
    cart = [];

    // 2️⃣ Clear localStorage
    localStorage.removeItem("swiftCart");

    // 3️⃣ Update UI (now empty)
    updateCartUI();

    // 4️⃣ Reload to trigger Flask notification toast
    location.reload();
}
 else {
            alert(data.error || "Order failed");
        }
    });
}



/* ---------------- PRODUCT PAGE QTY ---------------- */

function changeQuantity(productId, delta) {
    const qtySpan = document.getElementById(`qty-${productId}`);
    let current = parseInt(qtySpan.innerText);
    current += delta;
    if (current < 1) current = 1;
    qtySpan.innerText = current;
}
document.addEventListener("DOMContentLoaded", function() {
    updateCartUI();
});
