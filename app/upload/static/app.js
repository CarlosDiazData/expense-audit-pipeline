const REASON_LABELS = {
  INVALID_RFC: "RFC inválido",
  NON_DEDUCTIBLE_CATEGORY: "Categoría no deducible",
  RECEPTOR_NOT_COMPANY: "El receptor no es la empresa",
  MISSING_CRITICAL_FIELDS: "Faltan datos obligatorios",
  TOTAL_MISMATCH: "Los importes no cuadran",
  DATE_IN_FUTURE: "Fecha futura",
  INVALID_AMOUNT: "Importe inválido",
  PER_EXPENSE_LIMIT_EXCEEDED: "Excede el límite por gasto",
  MONTHLY_BUDGET_EXCEEDED: "Excede el presupuesto mensual",
  DUPLICATE_EXPENSE: "Posible gasto duplicado",
  CURRENCY_UNSUPPORTED: "Moneda no soportada",
};

const CATEGORY_LABELS = {
  FOOD: "Alimentos",
  TRANSPORT: "Transporte",
  SOFTWARE: "Software",
  LODGING: "Hospedaje",
  OTHER: "Otros",
};

const STATUS_LABELS = {
  VALID: "VÁLIDO",
  SUSPICIOUS: "SOSPECHOSO",
  NON_DEDUCTIBLE: "NO DEDUCIBLE",
};

const BADGE_CLASSES = {
  VALID: "valid",
  SUSPICIOUS: "suspicious",
  NON_DEDUCTIBLE: "non-deductible",
};

const ERROR_MESSAGES = {
  EXTRACTION_FAILED: "No se pudo extraer la información del documento.",
  UNSUPPORTED_DOCUMENT: "El documento no se pudo leer. Prueba con otro archivo.",
  FILE_TOO_LARGE: "El archivo excede el tamaño máximo permitido.",
  RETRY_EXHAUSTED: "El procesamiento falló después de varios intentos.",
};

const HTTP_MESSAGES = {
  400: "Tipo de archivo no soportado. Usa PDF, PNG o JPEG.",
  401: "Código de acceso incorrecto.",
  413: "El archivo excede el tamaño máximo permitido.",
  429: "Demasiadas solicitudes. Intenta de nuevo más tarde.",
  500: "No se pudo subir el archivo. Intenta de nuevo.",
  503: "El servicio no está disponible en este momento.",
};

const POLL_INTERVAL_MS = 2000;
const MAX_POLLS = 90;
const STALE_AFTER_MS = 5 * 60 * 1000;

const form = document.getElementById("upload-form");
const codeInput = document.getElementById("code");
const fileInput = document.getElementById("file");
const dropzone = document.getElementById("dropzone");
const dropzoneLabel = document.getElementById("dropzone-label");
const submitButton = document.getElementById("submit");
const progress = document.getElementById("progress");
const progressText = document.getElementById("progress-text");
const errorBox = document.getElementById("error");
const resultBox = document.getElementById("result");

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function hide(element) {
  element.classList.add("hidden");
}

function show(element) {
  element.classList.remove("hidden");
}

function resetOutput() {
  hide(errorBox);
  hide(resultBox);
  errorBox.textContent = "";
}

function showError(message) {
  errorBox.textContent = message;
  show(errorBox);
}

function showProgress(message) {
  progressText.textContent = message;
  show(progress);
}

function hideProgress() {
  hide(progress);
}

function setBusy(busy) {
  submitButton.disabled = busy;
  submitButton.textContent = busy ? "Procesando..." : "Enviar ticket";
}

function isStale(updatedAt) {
  if (!updatedAt) {
    return false;
  }
  const timestamp = Date.parse(updatedAt);
  return Number.isFinite(timestamp) && Date.now() - timestamp > STALE_AFTER_MS;
}

function renderResult(result) {
  if (!result) {
    showError("El gasto se completó pero no se encontró el resultado.");
    return;
  }

  const status = result.policy_status || "SUSPICIOUS";
  const badge = document.getElementById("badge");
  badge.textContent = STATUS_LABELS[status] || status;
  badge.className = `badge ${BADGE_CLASSES[status] || "suspicious"}`;

  document.getElementById("result-total").textContent = result.total
    ? `$${result.total} MXN`
    : "Sin total";
  document.getElementById("result-rfc").textContent = result.rfc_emisor || "No detectado";
  document.getElementById("result-category").textContent =
    CATEGORY_LABELS[result.category] || result.category || "Otros";
  document.getElementById("result-date").textContent = result.expense_date || "No detectada";

  const reasons = document.getElementById("reasons");
  reasons.innerHTML = "";
  (result.policy_reasons || []).forEach((code) => {
    const item = document.createElement("li");
    item.textContent = REASON_LABELS[code] || code;
    reasons.appendChild(item);
  });

  show(resultBox);
}

async function pollStatus(uploadId) {
  for (let attempt = 0; attempt < MAX_POLLS; attempt += 1) {
    await sleep(POLL_INTERVAL_MS);

    let response;
    try {
      response = await fetch(`/status/${uploadId}`);
    } catch {
      continue;
    }
    if (!response.ok) {
      continue;
    }

    const payload = await response.json();

    if (payload.status === "COMPLETED") {
      hideProgress();
      setBusy(false);
      renderResult(payload.result);
      return;
    }
    if (payload.status === "FAILED") {
      hideProgress();
      setBusy(false);
      showError(ERROR_MESSAGES[payload.error_code] || "El procesamiento del ticket falló.");
      return;
    }
    if (isStale(payload.updated_at)) {
      hideProgress();
      setBusy(false);
      showError("El procesamiento está tardando más de lo esperado. Intenta de nuevo en unos minutos.");
      return;
    }
  }

  hideProgress();
  setBusy(false);
  showError("El procesamiento está tardando más de lo esperado. Intenta de nuevo en unos minutos.");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetOutput();

  if (!fileInput.files.length) {
    showError("Selecciona un archivo antes de enviar.");
    return;
  }

  setBusy(true);
  showProgress("Subiendo ticket...");

  let response;
  try {
    response = await fetch("/upload", {
      method: "POST",
      body: new FormData(form),
    });
  } catch {
    hideProgress();
    setBusy(false);
    showError("No se pudo conectar con el servidor.");
    return;
  }

  if (!response.ok) {
    hideProgress();
    setBusy(false);
    showError(HTTP_MESSAGES[response.status] || "No se pudo subir el archivo.");
    return;
  }

  const payload = await response.json();
  showProgress("Procesando...");
  pollStatus(payload.upload_id);
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  dropzoneLabel.textContent = file ? file.name : "Arrastra tu archivo aquí o haz clic para seleccionarlo";
});

["dragenter", "dragover"].forEach((name) => {
  dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((name) => {
  dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (!file) {
    return;
  }
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  dropzoneLabel.textContent = file.name;
});
