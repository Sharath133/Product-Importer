import { initializeUpload } from "./upload.js";

const API_BASE = "";

document.addEventListener("DOMContentLoaded", () => {
    initializeUpload();
    initTabs();
    initProductsSection();
    initWebhooksSection();
});

function initTabs() {
    const buttons = document.querySelectorAll(".tab-button");
    const panels = document.querySelectorAll(".tab-panel");

    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            buttons.forEach((btn) => btn.classList.remove("active"));
            panels.forEach((panel) => panel.classList.remove("active"));

            button.classList.add("active");
            const target = button.getAttribute("data-target");
            const panel = document.getElementById(target);
            if (panel) {
                panel.classList.add("active");
            }
        });
    });
}

// Product management
let productPage = 1;
const productPageSize = 20;
let productTotalPages = 1;
let productFilters = {};
let editingProductId = null;

function initProductsSection() {
    const filtersForm = document.getElementById("product-filters");
    const resetFilters = document.getElementById("reset-filters");
    const newProductButton = document.getElementById("new-product-button");
    const bulkDeleteButton = document.getElementById("bulk-delete-button");
    const prevPageButton = document.getElementById("prev-page");
    const nextPageButton = document.getElementById("next-page");
    const productsTable = document.getElementById("products-body");

    filtersForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const data = new FormData(filtersForm);
        productFilters = {
            sku: data.get("sku") || document.getElementById("filter-sku").value.trim(),
            name: document.getElementById("filter-name").value.trim(),
            description: document.getElementById("filter-description").value.trim(),
            active: document.getElementById("filter-active").value,
        };
        productPage = 1;
        fetchProducts();
    });

    resetFilters.addEventListener("click", (event) => {
        event.preventDefault();
        filtersForm.reset();
        productFilters = {};
        productPage = 1;
        fetchProducts();
    });

    newProductButton.addEventListener("click", () => openProductDialog());

    bulkDeleteButton.addEventListener("click", async () => {
        const confirmed = await showConfirmationDialog(
            "Delete all products?",
            "This action cannot be undone. All products will be permanently removed."
        );
        if (!confirmed) return;
        try {
            const response = await fetch(`${API_BASE}/api/products/bulk`, {
                method: "DELETE",
            });
            if (!response.ok) {
                throw new Error("Failed to delete products.");
            }
            const data = await response.json();
            showMessage("products-message", `Deleted ${data.deleted} product(s).`, "success");
            fetchProducts();
        } catch (error) {
            showMessage("products-message", error.message, "error");
        }
    });

    prevPageButton.addEventListener("click", () => {
        if (productPage > 1) {
            productPage -= 1;
            fetchProducts();
        }
    });

    nextPageButton.addEventListener("click", () => {
        if (productPage < productTotalPages) {
            productPage += 1;
            fetchProducts();
        }
    });

    productsTable.addEventListener("click", (event) => {
        const target = event.target;
        if (target.matches("[data-edit]")) {
            const id = Number(target.getAttribute("data-edit"));
            const product = target.closest("tr").dataset.product
                ? JSON.parse(target.closest("tr").dataset.product)
                : null;
            openProductDialog(product, id);
        }

        if (target.matches("[data-delete]")) {
            const id = Number(target.getAttribute("data-delete"));
            const product = target.closest("tr").dataset.product
                ? JSON.parse(target.closest("tr").dataset.product)
                : { name: "this product" };
            deleteProduct(id, product.name ?? "this product");
        }
    });

    setupProductDialog();
    fetchProducts();
}

async function fetchProducts() {
    try {
        const params = new URLSearchParams({
            page: String(productPage),
            size: String(productPageSize),
        });

        if (productFilters.sku) params.set("sku", productFilters.sku);
        if (productFilters.name) params.set("name", productFilters.name);
        if (productFilters.description) params.set("description", productFilters.description);
        if (productFilters.active) params.set("active", productFilters.active);

        const response = await fetch(`${API_BASE}/api/products?${params.toString()}`);
        if (!response.ok) {
            throw new Error("Failed to load products.");
        }

        const data = await response.json();
        renderProducts(data.items);

        const pagination = data.pagination ?? {};
        const total = pagination.total ?? data.items.length;
        const size = pagination.size ?? productPageSize;
        productTotalPages = Math.max(1, Math.ceil(total / size));
        productPage = pagination.page ?? productPage;
        updatePaginationInfo(productPage, productTotalPages);
    } catch (error) {
        showMessage("products-message", error.message, "error");
    }
}

function renderProducts(products) {
    const tbody = document.getElementById("products-body");
    if (!products || products.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty">No products found.</td></tr>`;
        return;
    }

    tbody.innerHTML = "";
    for (const product of products) {
        const tr = document.createElement("tr");
        tr.dataset.product = JSON.stringify(product);
        tr.innerHTML = `
            <td>${product.sku}</td>
            <td>${escapeHtml(product.name)}</td>
            <td>${escapeHtml(product.description ?? "")}</td>
            <td><span class="status-pill ${product.active ? "" : "inactive"}">${product.active ? "Active" : "Inactive"}</span></td>
            <td>${new Date(product.updated_at).toLocaleString()}</td>
            <td class="table-actions">
                <button class="small-button secondary" data-edit="${product.id}">Edit</button>
                <button class="small-button danger" data-delete="${product.id}">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    }
}

function updatePaginationInfo(page, totalPages) {
    const info = document.getElementById("pagination-info");
    info.textContent = `Page ${page} of ${totalPages}`;

    document.getElementById("prev-page").disabled = page <= 1;
    document.getElementById("next-page").disabled = page >= totalPages;
}

function setupProductDialog() {
    const dialog = document.getElementById("product-dialog");
    const form = document.getElementById("product-form");
    const cancelButton = document.getElementById("product-cancel-button");
    const errorBox = document.getElementById("product-form-error");

    cancelButton.addEventListener("click", () => {
        dialog.close();
        form.reset();
        errorBox.classList.add("hidden");
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(form);
        const payload = {
            name: formData.get("name").toString().trim(),
            sku: formData.get("sku").toString().trim(),
            description: formData.get("description").toString().trim(),
            active: formData.get("active") === "on",
        };

        if (!payload.name || !payload.sku) {
            errorBox.textContent = "Name and SKU are required.";
            errorBox.classList.remove("hidden");
            return;
        }

        try {
            const method = editingProductId ? "PUT" : "POST";
            const url = editingProductId
                ? `${API_BASE}/api/products/${editingProductId}`
                : `${API_BASE}/api/products`;

            const response = await fetch(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || "Failed to save product.");
            }

            dialog.close();
            form.reset();
            editingProductId = null;
            errorBox.classList.add("hidden");
            fetchProducts();
            showMessage("products-message", "Product saved successfully.", "success");
        } catch (error) {
            errorBox.textContent = error.message;
            errorBox.classList.remove("hidden");
        }
    });
}

function openProductDialog(product = null, id = null) {
    const dialog = document.getElementById("product-dialog");
    const title = document.getElementById("product-form-title");
    const nameInput = document.getElementById("product-name");
    const skuInput = document.getElementById("product-sku");
    const descriptionInput = document.getElementById("product-description");
    const activeInput = document.getElementById("product-active");

    editingProductId = id;
    if (product) {
        title.textContent = "Edit Product";
        nameInput.value = product.name ?? "";
        skuInput.value = product.sku ?? "";
        descriptionInput.value = product.description ?? "";
        activeInput.checked = Boolean(product.active);
    } else {
        title.textContent = "New Product";
        nameInput.value = "";
        skuInput.value = "";
        descriptionInput.value = "";
        activeInput.checked = true;
    }

    dialog.showModal();
}

async function deleteProduct(id, name) {
    const confirmed = await showConfirmationDialog(
        "Delete product?",
        `Are you sure you want to delete "${name}"?`
    );
    if (!confirmed) return;

    try {
        const response = await fetch(`${API_BASE}/api/products/${id}`, { method: "DELETE" });
        if (!response.ok) {
            throw new Error("Failed to delete product.");
        }
        showMessage("products-message", "Product deleted.", "success");
        fetchProducts();
    } catch (error) {
        showMessage("products-message", error.message, "error");
    }
}

// Webhooks
let editingWebhookId = null;

function initWebhooksSection() {
    const newWebhookButton = document.getElementById("new-webhook-button");
    const webhooksTable = document.getElementById("webhooks-body");

    newWebhookButton.addEventListener("click", () => openWebhookDialog());
    setupWebhookDialog();

    webhooksTable.addEventListener("click", (event) => {
        const target = event.target;
        if (target.matches("[data-webhook-edit]")) {
            const row = target.closest("tr");
            const webhook = JSON.parse(row.dataset.webhook);
            openWebhookDialog(webhook, webhook.id);
        }

        if (target.matches("[data-webhook-delete]")) {
            const id = Number(target.getAttribute("data-webhook-delete"));
            deleteWebhook(id);
        }

        if (target.matches("[data-webhook-test]")) {
            const id = Number(target.getAttribute("data-webhook-test"));
            testWebhook(id);
        }
    });

    loadWebhooks();
}

async function loadWebhooks() {
    try {
        const response = await fetch(`${API_BASE}/api/webhooks`);
        if (!response.ok) {
            throw new Error("Failed to load webhooks.");
        }
        const data = await response.json();
        renderWebhooks(data);
    } catch (error) {
        showMessage("webhooks-message", error.message, "error");
    }
}

function renderWebhooks(webhooks) {
    const tbody = document.getElementById("webhooks-body");
    if (!webhooks || webhooks.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty">No webhooks configured.</td></tr>`;
        return;
    }

    tbody.innerHTML = "";
    for (const webhook of webhooks) {
        const tr = document.createElement("tr");
        tr.dataset.webhook = JSON.stringify(webhook);
        tr.innerHTML = `
            <td>${escapeHtml(webhook.url)}</td>
            <td>${webhook.event_type}</td>
            <td><span class="status-pill ${webhook.enabled ? "" : "inactive"}">${webhook.enabled ? "Enabled" : "Disabled"}</span></td>
            <td>${new Date(webhook.created_at).toLocaleString()}</td>
            <td class="table-actions">
                <button class="small-button secondary" data-webhook-edit="${webhook.id}">Edit</button>
                <button class="small-button info" data-webhook-test="${webhook.id}">Test</button>
                <button class="small-button danger" data-webhook-delete="${webhook.id}">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    }
}

function setupWebhookDialog() {
    const dialog = document.getElementById("webhook-dialog");
    const form = document.getElementById("webhook-form");
    const cancelButton = document.getElementById("webhook-cancel-button");
    const errorBox = document.getElementById("webhook-form-error");

    cancelButton.addEventListener("click", () => {
        dialog.close();
        form.reset();
        editingWebhookId = null;
        errorBox.classList.add("hidden");
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(form);
        const payload = {
            url: formData.get("url").toString(),
            event_type: formData.get("event_type").toString(),
            enabled: formData.get("enabled") === "on",
        };

        try {
            const method = editingWebhookId ? "PUT" : "POST";
            const url = editingWebhookId
                ? `${API_BASE}/api/webhooks/${editingWebhookId}`
                : `${API_BASE}/api/webhooks`;

            const response = await fetch(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || "Failed to save webhook.");
            }

            dialog.close();
            form.reset();
            editingWebhookId = null;
            errorBox.classList.add("hidden");
            loadWebhooks();
            showMessage("webhooks-message", "Webhook saved successfully.", "success");
        } catch (error) {
            errorBox.textContent = error.message;
            errorBox.classList.remove("hidden");
        }
    });
}

function openWebhookDialog(webhook = null, id = null) {
    const dialog = document.getElementById("webhook-dialog");
    const title = document.getElementById("webhook-form-title");
    const urlInput = document.getElementById("webhook-url");
    const eventInput = document.getElementById("webhook-event");
    const enabledInput = document.getElementById("webhook-enabled");

    editingWebhookId = id;
    if (webhook) {
        title.textContent = "Edit Webhook";
        urlInput.value = webhook.url;
        eventInput.value = webhook.event_type;
        enabledInput.checked = Boolean(webhook.enabled);
    } else {
        title.textContent = "Add Webhook";
        urlInput.value = "";
        eventInput.value = "product.created";
        enabledInput.checked = true;
    }

    dialog.showModal();
}

async function deleteWebhook(id) {
    const confirmed = await showConfirmationDialog(
        "Delete webhook?",
        "Webhook will no longer receive events."
    );
    if (!confirmed) return;

    try {
        const response = await fetch(`${API_BASE}/api/webhooks/${id}`, {
            method: "DELETE",
        });
        if (!response.ok) {
            throw new Error("Failed to delete webhook.");
        }
        loadWebhooks();
        showMessage("webhooks-message", "Webhook deleted.", "success");
    } catch (error) {
        showMessage("webhooks-message", error.message, "error");
    }
}

async function testWebhook(id) {
    try {
        const response = await fetch(`${API_BASE}/api/webhooks/${id}/test`, {
            method: "POST",
        });
        const payload = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(payload.detail || "Webhook test failed.");
        }

        showMessage(
            "webhooks-message",
            `Test sent. Status ${payload.status_code}, ${payload.response_time_ms} ms.`,
            "info"
        );
    } catch (error) {
        showMessage("webhooks-message", error.message, "error");
    }
}

// Utilities
function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return value
        .toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function showMessage(elementId, message, type = "info") {
    const element = document.getElementById(elementId);
    if (!element) return;
    element.textContent = message;
    element.classList.remove("hidden", "success", "error", "info");
    element.classList.add(type);
    if (element._timeoutId) {
        clearTimeout(element._timeoutId);
    }
    element._timeoutId = setTimeout(() => {
        element.classList.add("hidden");
        delete element._timeoutId;
    }, 5000);
}

async function showConfirmationDialog(title, message) {
    const template = document.getElementById("confirmation-template");
    const dialog = template.content.firstElementChild.cloneNode(true);

    dialog.querySelector("#confirm-title").textContent = title;
    dialog.querySelector("#confirm-message").textContent = message;
    document.body.appendChild(dialog);

    dialog.showModal();
    const result = await new Promise((resolve) => {
        dialog.addEventListener("close", () => {
            resolve(dialog.returnValue === "confirm");
        });
    });

    dialog.remove();
    return result;
}

