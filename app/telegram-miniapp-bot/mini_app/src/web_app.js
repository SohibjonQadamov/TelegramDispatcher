const productList = document.getElementById('product-list');
const orderButton = document.getElementById('order-button');

// Sample product data
const products = [
    { id: 1, name: 'Product 1', price: 100 },
    { id: 2, name: 'Product 2', price: 200 },
    { id: 3, name: 'Product 3', price: 300 },
];

// Function to display products
function displayProducts() {
    products.forEach(product => {
        const productItem = document.createElement('div');
        productItem.innerHTML = `
            <h3>${product.name}</h3>
            <p>Price: $${product.price}</p>
            <button onclick="buyProduct(${product.id})">Buyurtma berish</button>
        `;
        productList.appendChild(productItem);
    });
}

// Function to handle order submission
function buyProduct(productId) {
    const product = products.find(p => p.id === productId);
    if (product) {
        const orderData = {
            productId: product.id,
            productName: product.name,
            productPrice: product.price,
        };

        // Send order data to the bot
        fetch('https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                chat_id: '<CHAT_ID>',
                text: `New order: ${orderData.productName} for $${orderData.productPrice}`,
            }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                alert('Buyurtma yuborildi!');
            } else {
                alert('Xato yuz berdi. Iltimos, qayta urinib ko\'ring.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Xato yuz berdi. Iltimos, qayta urinib ko\'ring.');
        });
    }
}

// Initialize the app
displayProducts();