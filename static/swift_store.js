let cart = JSON.parse(localStorage.getItem("swiftCart")) || [];

// 🔥 STRONG CLEANUP FIX (improved)
if (!Array.isArray(cart) || cart.length === 0) {
    localStorage.removeItem("swiftCart");
    cart = [];
}


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

    // 🔥 ensure valid cart before saving
    if (!Array.isArray(cart)) {
        localStorage.removeItem("swiftCart");
        cart = [];
    }

    if (cart.length > 0) {
        localStorage.setItem("swiftCart", JSON.stringify(cart));
    } else {
        localStorage.removeItem("swiftCart");
    }

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

    // 🔥 SAME LOGIC (UNCHANGED — as you wanted)
    let deliveryFee = subtotal > 499 ? 0 : 25;
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

            <div style="margin-top:12px;">
                <select id="payment_method" style="
                    width:100%;
                    padding:10px;
                    border-radius:10px;
                    border:none;
                    background:#1e293b;
                    color:white;
                    font-weight:500;
                ">
                    <option value="COD">💵 Cash on Delivery</option>
                    <option value="ONLINE">💳 Pay Online (UPI)</option>
                </select>
            </div>

            <button class="checkout-btn" onclick="placeOrder()" 
                style="margin-top:12px;">
                Buy Now
            </button>
        </div>
    `;
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

    const method = document.getElementById("payment_method").value;

    fetch("/create-order", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            items: cart.map(item => ({
                product_id: item.id,
                quantity: item.quantity
            })),
            payment_method: method
        })
    })
    .then(res => res.json())
    .then(data => {

        if (data.success) {

            // 💳 ONLINE FLOW
            if (method === "ONLINE" && data.redirect) {
                window.location.href = data.redirect;
                return;
            }

            // 💵 COD FLOW
            cart = [];
            localStorage.removeItem("swiftCart");
            updateCartUI();
            location.reload();

        } else {
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


/* ---------------- INIT ---------------- */

document.addEventListener("DOMContentLoaded", function() {

    // 🔥 extra safety cleanup
    if (!Array.isArray(cart)) {
        localStorage.removeItem("swiftCart");
        cart = [];
    }

    updateCartUI();
});