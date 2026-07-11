const state = {
  projects: [],
  current: null,
  activeTab: "records",
  dataView: "buyer",
  jobTimer: null,
  researchTimer: null
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

async function api(path, options) {
  const response = await fetch(path, options || {});
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(payload.error || payload || ("请求失败：" + response.status));
  return payload;
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function pretty(value) { return JSON.stringify(value, null, 2); }

function showToast(message, error) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = "toast show" + (error ? " error" : "");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(function () { toast.className = "toast"; }, 3200);
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

function formatDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
  }).format(new Date(value));
}

function normalizeRecords(data) {
  if (Array.isArray(data)) return {globals: {}, records: data};
  if (!data || typeof data !== "object") return {globals: {}, records: []};
  if (!data.globals || typeof data.globals !== "object") data.globals = {};
  if (!Array.isArray(data.records)) data.records = [];
  return data;
}

function currentRecords() {
  if (!state.current) return {globals: {}, records: []};
  state.current.records = normalizeRecords(state.current.records);
  return state.current.records;
}

function recordCount(data) {
  const normalized = normalizeRecords(data);
  if (Array.isArray(normalized.pages)) {
    return normalized.pages.reduce(function (total, page) { return total + (Array.isArray(page.buyers) ? page.buyers.length : 0); }, 0);
  }
  return normalized.records.length;
}

function mappingCount(config) {
  if (config && config.cover && config.content) return 1;
  if (config && config.title_shape && Array.isArray(config.slots)) return 1;
  const staticCount = config && Array.isArray(config.slides) ? config.slides.length : 0;
  return staticCount + (config && config.repeat ? 1 : 0);
}

function chineseCount(value) {
  const matches = String(value || "").match(/[\u4e00-\u9fff]/g);
  return matches ? matches.length : 0;
}

function researchStrategyDefaults(need) {
  const value = String(need || "").toLowerCase();
  const generic = {
    preferred_industries: "当地制造企业、工程项目承包商、设备维护服务商、进口商和区域经销商",
    excluded_company_types: "仅销售同类产品且无进口、代理或自用场景的直接竞争制造商；无当地实体或无官网企业",
    custom_requirements: "企业需在目标国家有工厂、项目、服务网点或明确经销业务；优先有进口、代理、跨境采购或持续使用需求的公开证据。"
  };
  if (/电机|马达|motor/.test(value)) return {
    preferred_industries: "食品机械、包装机械、泵阀、风机、输送设备、暖通设备、矿山设备、物流仓储、工业自动化、工程承包和设备维护",
    excluded_company_types: "纯电机、发电机或减速电机制造商；仅销售电机且无进口代理或自用场景的品牌商；无当地实体企业",
    custom_requirements: "优先选择生产线、设备或项目必然使用电机的当地企业，以及进口商、代理商和维修服务商；必须说明电机的具体使用环节，并优先有进口或持续采购证据。"
  };
  if (/五轴|数控|cnc|机床|加工中心/.test(value)) return {
    preferred_industries: "航空航天零部件、汽车零部件、模具制造、医疗器械加工、精密机械、能源设备零部件、合同制造和CNC加工服务商",
    excluded_company_types: "五轴数控机床制造商、纯机床品牌商；无本地工厂、加工服务或经销网点的海外企业",
    custom_requirements: "企业必须在当地有工厂、机加工服务、维修网点或进口代理业务；优先有复杂零件加工、模具加工、五轴加工能力或进口机床代理的公开证据。"
  };
  return generic;
}

function applyResearchDefaults() {
  const defaults = researchStrategyDefaults($("#research-need").value.trim());
  ["preferred-industries", "excluded-company-types", "custom-requirements"].forEach(function (id) {
    const input = $("#" + id);
    const key = id.replaceAll("-", "_");
    const previous = input.dataset.autoDefault || "";
    if (!input.value.trim() || input.value.trim() === previous) {
      input.value = defaults[key];
      input.dataset.autoDefault = defaults[key];
    }
  });
}

function blankBuyer(country) {
  return {
    name: "", country: country || "", website: "", products: "", bio: "",
    logo_path: "", site_image_path: "", research_notes: "", buyer_type: "",
    demand_scenarios: "", local_presence: "", import_signal: "", evidence: "",
    source_urls: [], fit_score: 0, demand_score: 0, import_score: 0,
    verification_score: 0, total_score: 0, confidence: "", risks: ""
  };
}

function blankBriefingBuyer(index) {
  const letter = String.fromCharCode(65 + (index || 0));
  return {name: "", summary: "", products: ""};
}

function blankBriefingPage() {
  return {title: "", buyers: Array.from({length: 6}, function (_, index) { return blankBriefingBuyer(index); })};
}

function normalizeBriefing(data) {
  if (!data || typeof data !== "object") data = {globals: {}, pages: [blankBriefingPage()]};
  if (!data.globals || typeof data.globals !== "object") data.globals = {};
  if (!Array.isArray(data.pages)) data.pages = [blankBriefingPage()];
  data.pages.forEach(function (page) {
    if (!page || typeof page !== "object") return;
    if (!Array.isArray(page.buyers)) page.buyers = [];
    while (page.buyers.length < 6) page.buyers.push(blankBriefingBuyer(page.buyers.length));
    if (page.buyers.length > 6) page.buyers = page.buyers.slice(0, 6);
  });
  return data;
}

function currentBriefing() {
  if (!state.current) return {globals: {}, pages: [blankBriefingPage()]};
  state.current.records = normalizeBriefing(state.current.records);
  return state.current.records;
}

const MODEL_ROLES = ["research", "visual", "layout"];
const MODEL_PROVIDER_DEFAULTS = {
  openai: {label: "OpenAI", base_url: "https://api.openai.com/v1", research_model: "gpt-4.1", visual_model: "gpt-image-1", layout_model: "gpt-4.1", models: ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-image-1"]},
  deepseek: {label: "DeepSeek", base_url: "https://api.deepseek.com", research_model: "deepseek-chat", visual_model: "", layout_model: "deepseek-chat", models: ["deepseek-chat", "deepseek-reasoner"]},
  qwen: {label: "通义千问 / Qwen", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", research_model: "qwen-plus", visual_model: "", layout_model: "qwen-plus", models: ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"]},
  zhipu: {label: "智谱 GLM", base_url: "https://open.bigmodel.cn/api/paas/v4", research_model: "glm-4-plus", visual_model: "", layout_model: "glm-4-plus", models: ["glm-4-plus", "glm-4-air", "glm-4-flash"]},
  kimi: {label: "Kimi / Moonshot", base_url: "https://api.moonshot.cn/v1", research_model: "moonshot-v1-8k", visual_model: "", layout_model: "moonshot-v1-8k", models: ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]},
  doubao: {label: "豆包 / 火山方舟", base_url: "https://ark.cn-beijing.volces.com/api/v3", research_model: "", visual_model: "", layout_model: "", models: []},
  baidu: {label: "百度千帆 / 文心", base_url: "", research_model: "", visual_model: "", layout_model: "", models: []},
  minimax: {label: "MiniMax", base_url: "https://api.minimax.chat/v1", research_model: "", visual_model: "", layout_model: "", models: []},
  siliconflow: {label: "硅基流动 SiliconFlow", base_url: "https://api.siliconflow.cn/v1", research_model: "Qwen/Qwen2.5-72B-Instruct", visual_model: "", layout_model: "Qwen/Qwen2.5-72B-Instruct", models: ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1"]},
  openrouter: {label: "OpenRouter", base_url: "https://openrouter.ai/api/v1", research_model: "", visual_model: "", layout_model: "", models: []},
  ollama: {label: "本地 Ollama", base_url: "http://127.0.0.1:11434/v1", research_model: "qwen2.5", visual_model: "", layout_model: "qwen2.5", models: ["qwen2.5", "llama3.1", "deepseek-r1"]},
  lmstudio: {label: "本地 LM Studio", base_url: "http://127.0.0.1:1234/v1", research_model: "local-model", visual_model: "", layout_model: "local-model", models: ["local-model"]},
  compatible: {label: "自定义 OpenAI 兼容接口", base_url: "", research_model: "", visual_model: "", layout_model: "", models: []}
};

function setSelectValue(selector, value) {
  const element = $(selector);
  if (element) element.value = value || "deepseek";
}

function setInputValue(selector, value) {
  const element = $(selector);
  if (element) element.value = value || "";
}

function providerDefaults(provider) {
  return MODEL_PROVIDER_DEFAULTS[provider] || MODEL_PROVIDER_DEFAULTS.compatible;
}

function providerLabel(provider) {
  return providerDefaults(provider).label || provider;
}

function populateProviderSelects() {
  const options = Object.keys(MODEL_PROVIDER_DEFAULTS).map(function (key) {
    return '<option value="' + escapeHtml(key) + '">' + escapeHtml(providerLabel(key)) + '</option>';
  }).join("");
  ["unified"].concat(MODEL_ROLES).forEach(function (prefix) {
    const select = $("#" + prefix + "-provider");
    if (!select) return;
    const current = select.value || "deepseek";
    select.innerHTML = options;
    select.value = MODEL_PROVIDER_DEFAULTS[current] ? current : "compatible";
  });
}

function roleEnabled(role) {
  if (role === "research") return $("#enable-research-model").checked;
  if (role === "visual") return $("#enable-visual-model").checked;
  if (role === "layout") return $("#enable-layout-model").checked;
  return true;
}

function anyModelEnabled() {
  return MODEL_ROLES.some(roleEnabled);
}

function inferProviderFromRoleModel(role, provider) {
  const modelInput = $("#" + role + "-model");
  const model = (modelInput && modelInput.value || "").trim().toLowerCase();
  if ((!provider || provider === "openai" || provider === "compatible") && model.startsWith("deepseek")) return "deepseek";
  return provider || "deepseek";
}

function syncProviderFromModel(role) {
  const unified = $("#use-unified-model").checked;
  const targetPrefix = unified ? "unified" : role;
  const provider = inferProviderFromRoleModel(role, $("#" + targetPrefix + "-provider").value);
  if ($("#" + targetPrefix + "-provider").value !== provider) {
    $("#" + targetPrefix + "-provider").value = provider;
    const baseInput = $("#" + targetPrefix + "-base-url");
    if (baseInput) baseInput.value = providerDefaults(provider).base_url || "";
  }
}

function updateProviderDefaults(prefix) {
  const provider = $("#" + prefix + "-provider").value;
  const defaults = providerDefaults(provider);
  const baseInput = $("#" + prefix + "-base-url");
  if (baseInput) baseInput.value = defaults.base_url || "";
  const modelInput = $("#" + prefix + "-model");
  if (modelInput && defaults[prefix + "_model"]) modelInput.value = defaults[prefix + "_model"];
}

function activeProvider(role) {
  syncProviderFromModel(role);
  return $("#use-unified-model").checked ? $("#unified-provider").value : $("#" + role + "-provider").value;
}

function activeBaseUrl(role) {
  const provider = activeProvider(role);
  const value = $("#use-unified-model").checked ? $("#unified-base-url").value : $("#" + role + "-base-url").value;
  return value || providerDefaults(provider).base_url || "";
}

function activeApiKey(role) {
  if ($("#use-unified-model").checked) return $("#unified-api-key").value;
  const input = $("#" + role + "-api-key");
  return input ? input.value : "";
}

function fillModelOptions(role, models) {
  const list = $("#" + role + "-model-options");
  if (!list) return;
  list.innerHTML = (models || []).map(function (model) {
    return '<option value="' + escapeHtml(model) + '"></option>';
  }).join("");
  if (models && models.length && !$("#" + role + "-model").value.trim()) $("#" + role + "-model").value = models[0];
}


function ensureConsoleEnhancements() {
  const segmented = document.querySelector('.segmented');
  if (segmented && !document.querySelector('[data-data-view="briefing"]')) {
    const button = document.createElement('button');
    button.className = 'segment';
    button.dataset.dataView = 'briefing';
    button.type = 'button';
    button.textContent = '\u4e70\u5bb6\u5546\u60c5\u8868\u5355';
    segmented.insertBefore(button, segmented.querySelector('[data-data-view="json"]'));
  }
  const buyerView = document.getElementById('buyer-data-view');
  if (buyerView && !document.getElementById('briefing-data-view')) {
    const view = document.createElement('div');
    view.id = 'briefing-data-view';
    view.className = 'hidden';
    view.innerHTML = '<div class="briefing-help"><strong>\u4e70\u5bb6\u5546\u60c5\u89c4\u5219</strong><span>\u6bcf\u98751\u4e2a\u54c1\u7c7b\uff0c\u6bcf\u9875\u56fa\u5b9a6\u5bb6\u4e70\u5bb6\u3002\u6807\u9898\u53ea\u586b\u54c1\u7c7b\u540d\uff0c\u7b80\u4ecb\u8981\u5305\u542b\u4f01\u4e1a\u540d\u79f0\uff0c\u91c7\u8d2d\u54c1\u7c7b\u6309\u201c\u91c7\u8d2d\u54c1\u7c7b\uff1aXXXX\u7b49\u201d\u3002</span></div><div class="buyer-toolbar"><div><strong>\u4e70\u5bb6\u5546\u60c5</strong><span>\u4e00\u98756\u4e2a\u7d27\u51d1\u4e70\u5bb6\u6761\u76ee\uff0c\u5bfc\u51fa\u65f6\u4fdd\u7559\u6a21\u677f\u539f\u5b57\u4f53\u3001\u5b57\u53f7\u548c\u989c\u8272</span></div><div class="toolbar-actions"><button id="add-briefing-page" class="secondary-action" type="button">\u6dfb\u52a0\u54c1\u7c7b\u9875</button><button id="save-briefing" type="button">\u4fdd\u5b58\u5546\u60c5\u8d44\u6599</button></div></div><div id="briefing-list" class="briefing-list"></div>';
    buyerView.insertAdjacentElement('afterend', view);
  }
  const layoutPanel = document.getElementById('panel-layout');
  const layoutEditor = document.getElementById('layout-editor');
  if (layoutPanel && layoutEditor && !document.getElementById('layout-guide')) {
    const guide = document.createElement('div');
    guide.id = 'layout-guide';
    guide.className = 'layout-guide';
    guide.innerHTML = '<div><strong>\u7248\u5f0f\u6620\u5c04\u600e\u4e48\u586b</strong><p>\u5148\u5230\u201c\u6a21\u677f\u7ed3\u6784\u201d\u67e5\u770b\u6bcf\u4e2a\u6587\u672c\u6846\u6216\u56fe\u7247\u6846\u7684\u7d22\u5f15\uff0c\u518d\u628a\u5b57\u6bb5\u6620\u5c04\u5230\u5bf9\u5e94 shape_index\u3002\u4e0d\u786e\u5b9a\u65f6\u5148\u63d2\u5165\u793a\u4f8b\uff0c\u518d\u6539\u7d22\u5f15\u3002</p></div><div class="layout-guide-actions"><button data-layout-example="generic" type="button">\u63d2\u5165\u901a\u7528\u793a\u4f8b</button><button data-layout-example="buyer_board" type="button">\u63d2\u5165\u4e70\u5bb6\u770b\u677f\u793a\u4f8b</button><button data-layout-example="buyer_briefing" type="button">\u63d2\u5165\u4e70\u5bb6\u5546\u60c5\u793a\u4f8b</button></div>';
    layoutEditor.parentNode.insertBefore(guide, layoutEditor);
  }
}

function renderProjects() {
  $("#project-count").textContent = state.projects.length;
  const list = $("#project-list");
  if (!state.projects.length) {
    list.innerHTML = '<div class="structure-empty">还没有项目</div>';
    return;
  }
  list.innerHTML = state.projects.map(function (item) {
    const active = state.current && state.current.project.slug === item.slug ? "active" : "";
    const ready = item.template_ready ? "ready" : "";
    const status = item.template_ready ? "模板已上传" : "等待模板";
    return '<button class="project-item ' + active + ' ' + ready + '" data-slug="' + escapeHtml(item.slug) + '" type="button">' +
      '<span class="project-indicator"></span><span class="project-copy">' +
      '<strong>' + escapeHtml(item.name) + '</strong><small>' + status + ' · ' + formatDate(item.updated_at) + '</small>' +
      '</span></button>';
  }).join("");
  $$(".project-item").forEach(function (button) {
    button.addEventListener("click", function () { loadProject(button.dataset.slug); });
  });
}

function updateSteps() {
  const ready = state.current && state.current.template.ready;
  const records = recordCount(state.current && state.current.records);
  const mappings = mappingCount(state.current && state.current.layout_config);
  $("#step-template").className = "step " + (ready ? "done" : "active");
  $("#step-records").className = "step " + (records ? "done" : ready ? "active" : "");
  $("#step-layout").className = "step " + (mappings ? "done" : records ? "active" : "");
  $("#step-export").className = "step " + (state.current && state.current.outputs.length ? "done" : mappings ? "active" : "");
}

function renderStructure(template) {
  const view = $("#structure-view");
  if (!template.ready) {
    $("#structure-summary").textContent = "请先上传模板";
    view.innerHTML = '<div class="structure-empty">上传 PPTX 后，这里会显示每页形状、索引、文本摘要和位置。</div>';
    return;
  }
  if (template.error) {
    $("#structure-summary").textContent = template.error;
    view.innerHTML = '<div class="structure-empty">' + escapeHtml(template.error) + '</div>';
    return;
  }
  $("#structure-summary").textContent = template.slide_count + " 页 · " + template.width + " × " + template.height + " 英寸";
  view.innerHTML = template.slides.map(function (slide) {
    const rows = slide.shapes.map(function (shape) {
      return '<tr><td>' + shape.index + '</td><td>' + escapeHtml(shape.name) + (shape.has_table ? " · 表格" : "") +
        '</td><td>' + escapeHtml(shape.text || "—") + '</td><td>' + shape.left + ", " + shape.top + " · " +
        shape.width + " × " + shape.height + '</td></tr>';
    }).join("");
    return '<details class="slide-row"><summary><span>第 ' + slide.index + ' 页</span><span>' +
      slide.shape_count + ' 个元素</span></summary><table class="shape-table"><thead><tr>' +
      '<th>索引</th><th>名称</th><th>文本摘要</th><th>位置与大小（英寸）</th></tr></thead><tbody>' +
      rows + '</tbody></table></details>';
  }).join("");
}

function renderOutputs(outputs) {
  $("#outputs-summary").textContent = outputs.length + " 个文件";
  const list = $("#output-list");
  if (!outputs.length) {
    list.innerHTML = '<div class="output-empty">还没有导出文件</div>';
    return;
  }
  const slug = state.current.project.slug;
  list.innerHTML = outputs.map(function (item) {
    const href = "/api/projects/" + encodeURIComponent(slug) + "/output/" + encodeURIComponent(item.name);
    const preview = item.preview_count ? '<button class="output-preview" data-preview-name="' + escapeHtml(item.name) + '" data-preview-count="' + item.preview_count + '" type="button">预览</button>' : '';
    return '<div class="output-item"><strong>' + escapeHtml(item.name) + '</strong><small>' +
      formatBytes(item.size) + " · " + formatDate(item.modified_at) +
      '</small><div class="output-actions">' + preview + '<a href="' + href + '">下载</a></div></div>';
  }).join("");
  $$(".output-preview").forEach(function (button) {
    button.addEventListener("click", function () {
      openPreview(button.dataset.previewName, Number(button.dataset.previewCount || 0));
    });
  });
}

function sourceSlideIndex() {
  return Number(state.current && state.current.project && state.current.project.generic_source_slide ||
    state.current && state.current.layout_config && state.current.layout_config.repeat && state.current.layout_config.repeat.source_slide_index || 1);
}

function renderPagePicker(template) {
  const picker = $("#page-picker");
  if (!picker) return;
  const selected = sourceSlideIndex();
  const slides = template && template.slides || [];
  if (!slides.length) {
    picker.innerHTML = '<div class="page-picker-empty">上传模板后可选择批量页面。</div>';
    return;
  }
  picker.innerHTML = slides.map(function (slide) {
    const text = (slide.shapes || []).filter(function (shape) { return shape.text; }).slice(0, 3).map(function (shape) { return shape.text; }).join(" · ");
    return '<button class="page-card ' + (slide.index === selected ? 'selected' : '') + '" data-source-slide="' + slide.index + '" type="button"><span>第 ' + slide.index + ' 页</span><small>' + escapeHtml(text || '版式页面') + '</small></button>';
  }).join("");
  $$("[data-source-slide]").forEach(function (button) {
    button.addEventListener("click", function () {
      state.current.project.generic_source_slide = Number(button.dataset.sourceSlide);
      renderPagePicker(state.current.template);
      showToast("已选择第 " + button.dataset.sourceSlide + " 页作为批量页面");
    });
  });
}

function renderMappingPreview(preview) {
  const host = $("#mapping-preview");
  if (!host) return;
  const entries = preview && preview.entries || [];
  const warnings = preview && preview.warnings || [];
  const rows = entries.map(function (entry) {
    return '<div class="mapping-row"><span class="mapping-target">' + escapeHtml(entry.target) + '</span><span class="mapping-arrow">&#8594;</span><span><strong>' + escapeHtml(entry.field) + '</strong><small>' + escapeHtml(entry.sample || '当前暂无示例值') + '</small></span></div>';
  }).join("");
  const notices = warnings.map(function (warning) { return '<p class="mapping-warning">' + escapeHtml(warning) + '</p>'; }).join("");
  host.innerHTML = rows || '<div class="mapping-empty">生成映射后，这里会显示每个字段的实际落点。</div>';
  if (notices) host.innerHTML += '<div class="mapping-warnings">' + notices + '</div>';
}

function renderRecipes(recipes) {
  const list = $("#recipe-list");
  if (!list) return;
  if (!recipes || !recipes.length) {
    list.innerHTML = '<span class="recipe-empty">还没有保存的版式方案</span>';
    return;
  }
  list.innerHTML = recipes.map(function (recipe) {
    return '<button class="recipe-item" data-recipe-id="' + escapeHtml(recipe.id) + '" type="button"><strong>' + escapeHtml(recipe.name) + '</strong><small>' + formatDate(recipe.created_at) + '</small></button>';
  }).join("");
  $$("[data-recipe-id]").forEach(function (button) {
    button.addEventListener("click", function () { applyLayoutRecipe(button.dataset.recipeId); });
  });
}

async function refreshLayoutPreview(config) {
  if (!state.current || state.current.project.mode !== "generic") return;
  try {
    const result = await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/layout-preview", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({layout_config: config || state.current.layout_config})
    });
    state.layoutPreview = result;
    renderMappingPreview(result);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function saveLayoutRecipe() {
  if (!state.current) return;
  const name = $("#recipe-name").value.trim();
  if (!name) { showToast("请填写版式方案名称", true); return; }
  try {
    const result = await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/layout-recipes", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name: name, instruction: $("#layout-instruction").value.trim()})
    });
    state.current.project.layout_recipes = result.recipes;
    $("#recipe-name").value = "";
    renderRecipes(result.recipes);
    showToast("版式方案已保存");
  } catch (error) { showToast(error.message, true); }
}

async function applyLayoutRecipe(recipeId) {
  if (!state.current) return;
  try {
    const result = await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/layout-recipes/" + encodeURIComponent(recipeId) + "/apply", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
    state.current.layout_config = result.layout_config;
    $("#layout-editor").value = pretty(result.layout_config);
    $("#layout-instruction").value = result.recipe.instruction || "";
    renderPagePicker(state.current.template);
    renderMappingPreview(result.preview);
    updateSteps();
    showToast("已应用版式方案：" + result.recipe.name);
  } catch (error) { showToast(error.message, true); }
}

function openPreview(filename, count) {
  if (!state.current || !count) return;
  const slug = state.current.project.slug;
  $("#preview-title").textContent = filename;
  $("#preview-gallery").innerHTML = Array.from({length: count}, function (_, index) {
    const page = index + 1;
    const src = "/api/projects/" + encodeURIComponent(slug) + "/preview/" + encodeURIComponent(filename) + "/" + page;
    return '<figure><img src="' + src + '" alt="第 ' + page + ' 页预览" loading="' + (page > 2 ? 'lazy' : 'eager') + '"><figcaption>第 ' + page + ' 页</figcaption></figure>';
  }).join("");
  $("#preview-modal").classList.remove("hidden");
}

function closePreview() {
  $("#preview-modal").classList.add("hidden");
  $("#preview-gallery").innerHTML = "";
}

function updateModelBadge() {
  if (!state.current) return;
  const settings = state.current.model_settings || {};
  if (settings.research_enabled === false) {
    $("#research-model-status").textContent = "\u624b\u52a8/\u5bfc\u5165\u6a21\u5f0f\uff0c\u65e0\u9700\u6a21\u578b Key";
    $("#research-model-status").className = "model-badge ready";
    return;
  }
  const ready = settings.unified ? settings.unified_configured : settings.research_configured;
  $("#research-model-status").textContent = ready ? "\u68c0\u7d22\u6a21\u578b\u5df2\u914d\u7f6e" : "\u9700\u8981\u914d\u7f6e\u6a21\u578b Key";
  $("#research-model-status").className = "model-badge" + (ready ? " ready" : "");
}

function buyerEntryHtml(buyer, index) {
  const count = chineseCount(buyer.bio);
  const title = buyer.name || ("买家 " + (index + 1));
  const logoState = buyer.logo_path ? '<span class="ready">Logo 已获取</span>' : '<span>Logo 未获取</span>';
  const siteState = buyer.site_image_path ? '<span class="ready">右侧图片已获取</span>' : '<span>右侧图片未获取</span>';
  const score = Number(buyer.total_score || 0);
  const sourceCount = Array.isArray(buyer.source_urls) ? buyer.source_urls.length : 0;
  const qualification = score || buyer.demand_scenarios || buyer.evidence ? '<details class="qualification">' +
    '<summary><span>匹配评分 <strong>' + score + '</strong></span><span>' + escapeHtml(buyer.buyer_type || "待分类") + ' · ' + sourceCount + ' 条来源</span></summary>' +
    '<div class="score-grid"><span>业务匹配<strong>' + Number(buyer.fit_score || 0) + '</strong></span><span>必然需求<strong>' + Number(buyer.demand_score || 0) + '</strong></span><span>进口信号<strong>' + Number(buyer.import_score || 0) + '</strong></span><span>证据质量<strong>' + Number(buyer.verification_score || 0) + '</strong></span></div>' +
    '<dl><dt>需求场景</dt><dd>' + escapeHtml(buyer.demand_scenarios || "未说明") + '</dd><dt>当地业务</dt><dd>' + escapeHtml(buyer.local_presence || "未说明") + '</dd><dt>进口/采购信号</dt><dd>' + escapeHtml(buyer.import_signal || "暂无公开证据") + '</dd><dt>证据与风险</dt><dd>' + escapeHtml((buyer.evidence || "") + (buyer.risks ? "；风险：" + buyer.risks : "")) + '</dd></dl></details>' : '';
  return '<article class="buyer-entry" data-index="' + index + '">' +
    '<div class="buyer-entry-head"><div class="buyer-entry-title"><span class="buyer-index">' + (index + 1) +
    '</span><strong>' + escapeHtml(title) + '</strong></div><button class="remove-buyer" data-remove="' + index +
    '" type="button" title="删除买家">×</button></div><div class="buyer-fields">' +
    '<div class="buyer-field"><label>企业全称<input data-buyer-index="' + index + '" data-field="name" value="' +
    escapeHtml(buyer.name) + '" placeholder="企业正式名称"></label></div>' +
    '<div class="buyer-field"><label>国家<input data-buyer-index="' + index + '" data-field="country" value="' +
    escapeHtml(buyer.country) + '" placeholder="国家或地区"></label></div>' +
    '<div class="buyer-field"><label>企业官网<input data-buyer-index="' + index + '" data-field="website" value="' +
    escapeHtml(buyer.website) + '" placeholder="www.example.com"></label></div>' +
    '<div class="buyer-field products"><label>采购产品<input data-buyer-index="' + index + '" data-field="products" value="' +
    escapeHtml(buyer.products) + '" placeholder="用中文顿号分隔具体采购产品"></label></div>' +
    '<div class="buyer-field bio"><label>企业简介<textarea data-buyer-index="' + index + '" data-field="bio" placeholder="填写120-130个中文字符的完整企业介绍">' +
    escapeHtml(buyer.bio) + '</textarea></label><div class="field-meta ' + (count >= 120 && count <= 130 ? "good" : "") +
    '" data-bio-count="' + index + '">' + count + ' / 120-130 个中文字符</div></div>' +
    '<div class="asset-state">' + logoState + siteState + '</div>' + qualification + '</div></article>';
}

function renderBuyerForm() {
  const data = currentRecords();
  const globals = data.globals;
  const research = state.current.project.research || {};
  $("#research-country").value = globals.country || research.country || "";
  $("#research-need").value = globals.procurement_need || research.procurement_need || "";
  $("#research-count").value = research.buyer_count || Math.max(data.records.length, 10);
  const strategy = state.current.project.research_strategy || {};
  $("#preferred-industries").value = strategy.preferred_industries || "";
  $("#excluded-company-types").value = strategy.excluded_company_types || "";
  $("#custom-requirements").value = strategy.custom_requirements || "";
  $("#prefer-import-evidence").checked = strategy.prefer_import_evidence !== false;
  $("#candidate-multiplier").value = strategy.candidate_multiplier || 3;
  const defaults = researchStrategyDefaults($("#research-need").value.trim());
  [["#preferred-industries", "preferred_industries"], ["#excluded-company-types", "excluded_company_types"], ["#custom-requirements", "custom_requirements"]].forEach(function (item) {
    if ($(item[0]).value.trim() === defaults[item[1]]) $(item[0]).dataset.autoDefault = defaults[item[1]];
  });
  applyResearchDefaults();
  $("#records-summary").textContent = data.records.length + " 家买家";
  const list = $("#buyer-list");
  if (!data.records.length) {
    list.innerHTML = '<div class="buyer-empty">还没有买家资料。可以使用上方搜索生成，或点击“添加买家”手动录入。</div>';
  } else {
    list.innerHTML = data.records.map(buyerEntryHtml).join("");
  }
  $$("[data-buyer-index]").forEach(function (input) {
    input.addEventListener("input", function () {
      const index = Number(input.dataset.buyerIndex);
      const field = input.dataset.field;
      currentRecords().records[index][field] = input.value;
      if (field === "bio") {
        const count = chineseCount(input.value);
        const meta = $('[data-bio-count="' + index + '"]');
        meta.textContent = count + " / 120-130 个中文字符";
        meta.classList.toggle("good", count >= 120 && count <= 130);
      }
      if (field === "name") {
        const heading = input.closest(".buyer-entry").querySelector(".buyer-entry-title strong");
        heading.textContent = input.value || ("买家 " + (index + 1));
      }
    });
  });
  $$("[data-remove]").forEach(function (button) {
    button.addEventListener("click", function () {
      currentRecords().records.splice(Number(button.dataset.remove), 1);
      renderBuyerForm();
      updateSteps();
    });
  });
}


function briefingEntryHtml(page, pageIndex) {
  const buyers = page.buyers || [];
  const buyerRows = buyers.map(function (buyer, buyerIndex) {
    const products = String(buyer.products || "").startsWith("\u91c7\u8d2d\u54c1\u7c7b\uff1a") ? buyer.products : (buyer.products ? "\u91c7\u8d2d\u54c1\u7c7b\uff1a" + buyer.products : "");
    return '<div class="briefing-buyer" data-page-index="' + pageIndex + '" data-briefing-buyer="' + buyerIndex + '"><div class="briefing-buyer-head"><span>' + (buyerIndex + 1) + '</span><strong>' + escapeHtml(buyer.name || ('\u4e70\u5bb6 ' + (buyerIndex + 1))) + '</strong></div><label>\u4f01\u4e1a\u540d\u79f0<input data-briefing-field="name" value="' + escapeHtml(buyer.name || '') + '" placeholder="\u4f8b\u5982 Americana Group"></label><label>\u4e70\u5bb6\u7b80\u4ecb<textarea data-briefing-field="summary" placeholder="\u63a5\u8fd140\u4e2a\u4e2d\u6587\u5b57\uff0c\u5fc5\u987b\u5305\u542b\u4f01\u4e1a\u540d\u79f0">' + escapeHtml(buyer.summary || buyer.intro || '') + '</textarea></label><label>\u91c7\u8d2d\u54c1\u7c7b<input data-briefing-field="products" value="' + escapeHtml(products) + '" placeholder="\u91c7\u8d2d\u54c1\u7c7b\uff1a\u70d8\u7119\u7089\u3001\u6405\u62cc\u673a\u3001\u5305\u88c5\u8bbe\u5907\u7b49"></label></div>';
  }).join('');
  return '<article class="briefing-page" data-page-index="' + pageIndex + '"><div class="briefing-page-head"><label>\u54c1\u7c7b\u6807\u9898<input data-briefing-title="' + pageIndex + '" value="' + escapeHtml(page.title || '') + '" placeholder="\u53ea\u586b\u54c1\u7c7b\uff0c\u4f8b\u5982 \u70d8\u7119\u673a\u68b0"></label><button class="remove-briefing-page" data-remove-briefing-page="' + pageIndex + '" type="button">\u5220\u9664\u672c\u9875</button></div><div class="briefing-buyers">' + buyerRows + '</div></article>';
}

function renderBriefingForm() {
  ensureConsoleEnhancements();
  const data = currentBriefing();
  const pages = data.pages || [];
  const total = recordCount(data);
  $("#records-summary").textContent = pages.length + " \u9875 / " + total + " \u5bb6\u4e70\u5bb6";
  const list = $("#briefing-list");
  if (!list) return;
  list.innerHTML = pages.map(briefingEntryHtml).join("");
  $$('[data-briefing-title]').forEach(function (input) {
    input.addEventListener('input', function () { data.pages[Number(input.dataset.briefingTitle)].title = input.value; });
  });
  $$('[data-briefing-field]').forEach(function (input) {
    input.addEventListener('input', function () {
      const card = input.closest('[data-page-index]');
      const pageIndex = Number(card.dataset.pageIndex);
      const buyerIndex = Number(input.closest('[data-briefing-buyer]').dataset.briefingBuyer);
      let value = input.value;
      if (input.dataset.briefingField === 'products' && value && !value.startsWith('\u91c7\u8d2d\u54c1\u7c7b\uff1a')) value = '\u91c7\u8d2d\u54c1\u7c7b\uff1a' + value;
      data.pages[pageIndex].buyers[buyerIndex][input.dataset.briefingField] = value;
    });
  });
  $$('[data-remove-briefing-page]').forEach(function (button) {
    button.addEventListener('click', function () {
      if (data.pages.length <= 1) { showToast('\u81f3\u5c11\u4fdd\u75591\u9875\u4e70\u5bb6\u5546\u60c5', true); return; }
      data.pages.splice(Number(button.dataset.removeBriefingPage), 1);
      renderBriefingForm();
      updateSteps();
    });
  });
}

async function persistBriefingData(showMessage) {
  const data = currentBriefing();
  await api('/api/projects/' + encodeURIComponent(state.current.project.slug) + '/document/records', {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
  });
  state.current.records = data;
  $('#records-editor').value = pretty(data);
  if (showMessage !== false) showToast('\u4e70\u5bb6\u5546\u60c5\u8d44\u6599\u5df2\u4fdd\u5b58');
}

function layoutExample(kind) {
  if (kind === 'buyer_briefing') return {title_shape: 5, buyers_per_slide: 6, slots: [{summary_shape: 15, products_shape: 23}, {summary_group: 16, summary_child: 2, products_group: 16, products_child: 3}, {summary_group: 17, summary_child: 2, products_group: 17, products_child: 3}, {summary_shape: 19, products_shape: 26}, {summary_shape: 20, products_shape: 25}, {summary_shape: 22, products_shape: 24}]};
  if (kind === 'buyer_board') return {version: 1, defaults: {cover_title: 'Buyer Board', cover_country: ''}, cover: {slide_index: 1, title_shape: 1}, content: {source_slide_index: 2, start_slide_index: 2, title_shape: 1, table_shape: 2, rows: {name: 1, website: 2, products: 3, bio: 4}, images: {logo_shape: 3, site_shape: 4}}};
  return {version: 1, record_key: 'records', required_fields: ['name', 'summary'], slides: [{slide_index: 1, texts: [{shape_index: 3, field: 'globals.deck_title'}, {shape_index: 5, template: '{record.name}|{record.summary}'}]}], repeat: {source_slide_index: 2, start_slide_index: 2, template_slide_count: 1, trim_extra_template_slides: true, texts: [{shape_index: 4, field: 'name'}, {shape_index: 8, field: 'summary'}], images: [{shape_index: 12, field: 'image_path', fit: 'cover', clear_if_missing: true}]}};
}

function renderProject() {
  const data = state.current;
  $("#empty-state").classList.add("hidden");
  $("#workspace").classList.remove("hidden");
  $("#project-title").textContent = data.project.name;
  $("#project-meta").innerHTML = '<span>' + escapeHtml(data.project.slug) + '</span><span>' +
    (data.template.ready ? data.template.slide_count + " 页模板" : "未上传模板") + '</span>';
  data.records = data.project.mode === "buyer_briefing" ? normalizeBriefing(data.records) : normalizeRecords(data.records);
  $("#records-editor").value = pretty(data.records);
  $("#layout-editor").value = pretty(data.layout_config);
  $("#layout-instruction").value = data.project.layout_instruction || "";
  if (!data.project.generic_source_slide) data.project.generic_source_slide = data.layout_config && data.layout_config.repeat && data.layout_config.repeat.source_slide_index || Math.min(2, Math.max(1, Number(data.template.slide_count || 1)));
  $("#layout-summary").textContent = mappingCount(data.layout_config) ?
    (data.layout_config.cover ? "买家看板映射已就绪" : mappingCount(data.layout_config) + " 组页面映射") : "尚未配置映射";
  $("#output-filename").value = data.project.export && data.project.export.filename || "finished.pptx";
  $("#strict-mode").checked = Boolean(data.project.export && data.project.export.strict);
  $("#presentation-engine").value = data.project.export && data.project.export.presentation_engine || "auto";
  if (data.project.mode === "buyer_briefing") renderBriefingForm();
  else renderBuyerForm();
  $("#import-band").classList.remove("hidden");
  $("#presentation-engine-row").classList.toggle("hidden", data.project.mode !== "generic");
  $$("[data-data-view]").forEach(function (button) {
    const view = button.dataset.dataView;
    const visible = view === "json" ||
      (view === "buyer" && data.project.mode === "buyer_board") ||
      (view === "briefing" && data.project.mode === "buyer_briefing");
    button.classList.toggle("hidden", !visible);
  });
  setDataView(data.project.mode === "buyer_board" ? "buyer" : (data.project.mode === "buyer_briefing" ? "briefing" : "json"), false);
  renderStructure(data.template);
  renderOutputs(data.outputs);
  $("#generic-layout-tools").classList.toggle("hidden", data.project.mode !== "generic");
  if (data.project.mode === "generic") {
    renderPagePicker(data.template);
    renderRecipes(data.project.layout_recipes || []);
    refreshLayoutPreview(data.layout_config);
  }
  updateModelBadge();
  updateSteps();
  renderProjects();
}

async function refreshProjects(selectSlug) {
  const payload = await api("/api/projects");
  state.projects = payload.projects;
  renderProjects();
  if (selectSlug) await loadProject(selectSlug);
}

async function loadProject(slug) {
  try {
    state.current = await api("/api/projects/" + encodeURIComponent(slug));
    renderProject();
  } catch (error) {
    showToast(error.message, true);
  }
}
function parseEditor(selector, label) {
  try {
    return JSON.parse($(selector).value);
  } catch (error) {
    throw new Error(label + " JSON 格式错误：" + error.message);
  }
}

async function saveDocument(kind) {
  if (!state.current) return;
  const isRecords = kind === "records";
  try {
    const selector = isRecords ? "#records-editor" : "#layout-editor";
    const payload = parseEditor(selector, isRecords ? "数据" : "版式映射");
    await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/document/" + kind, {
      method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
    if (isRecords) state.current.records = normalizeRecords(payload);
    else state.current.layout_config = payload;
    renderProject();
    showToast(isRecords ? "JSON 数据已保存" : "版式映射已保存");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function persistBuyerData(showMessage) {
  if (!state.current) return null;
  const data = currentRecords();
  data.globals.country = $("#research-country").value.trim();
  data.globals.procurement_need = $("#research-need").value.trim();
  const result = await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/buyer-data", {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      country: data.globals.country,
      procurement_need: data.globals.procurement_need,
      buyers: data.records
    })
  });
  state.current.records = result.records;
  state.current.layout_config = result.layout_config;
  state.current.project.mode = "buyer_board";
  $("#records-editor").value = pretty(result.records);
  $("#layout-editor").value = pretty(result.layout_config);
  renderBuyerForm();
  updateSteps();
  if (showMessage !== false) {
    if (result.warnings && result.warnings.length) showToast(result.warnings[0], true);
    else showToast("买家资料和版式映射已保存");
  }
  return result;
}

async function uploadTemplate(file) {
  if (!state.current || !file) return;
  if (!file.name.toLowerCase().endsWith(".pptx")) {
    showToast("请选择 PPTX 模板文件", true);
    return;
  }
  const slug = state.current.project.slug;
  try {
    showToast("正在读取并分析模板...");
    const template = await api("/api/projects/" + encodeURIComponent(slug) + "/template", {
      method: "POST",
      headers: {"Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
      body: await file.arrayBuffer()
    });
    await refreshProjects();
    await loadProject(slug);
    if (template.layout_warning) showToast(template.layout_warning, true);
    else showToast("模板已上传，共 " + template.slide_count + " 页");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    $("#template-file").value = "";
  }
}

async function importRecordsFile(file) {
  if (!state.current || !file) return;
  const suffix = file.name.toLowerCase().slice(file.name.lastIndexOf("."));
  if (![".txt", ".md", ".csv", ".json", ".docx"].includes(suffix)) {
    showToast("资料导入支持 TXT、Markdown、CSV、JSON、DOCX", true);
    return;
  }
  try {
    $("#import-status").textContent = "正在识别 " + file.name;
    const query = "?filename=" + encodeURIComponent(file.name) + "&instruction=" + encodeURIComponent($("#import-instruction").value.trim());
    const result = await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/import-records" + query, {
      method: "POST",
      headers: {"Content-Type": "application/octet-stream"},
      body: await file.arrayBuffer()
    });
    state.current.records = state.current.project.mode === "buyer_briefing" ? normalizeBriefing(result.records) : normalizeRecords(result.records);
    if (result.layout_config) state.current.layout_config = result.layout_config;
    $("#records-editor").value = pretty(state.current.records);
    $("#import-status").textContent = "已导入 " + result.source + "，生成 " + result.record_count + " 条记录";
    setDataView(state.current.project.mode === "buyer_board" ? "buyer" : (state.current.project.mode === "buyer_briefing" ? "briefing" : "json"), false);
    updateSteps();
    showToast("资料已识别并写入 records.json");
  } catch (error) {
    $("#import-status").textContent = "导入失败";
    showToast(error.message, true);
  } finally {
    $("#records-file").value = "";
  }
}

async function importPastedText() {
  const input = $("#import-text");
  const text = input.value.trim();
  if (!text) {
    showToast("\u8bf7\u5148\u7c98\u8d34\u8981\u8bc6\u522b\u7684\u8d44\u6599", true);
    return;
  }
  const file = new File([text], "pasted-data.txt", {type: "text/plain;charset=utf-8"});
  await importRecordsFile(file);
  input.value = "";
}

async function generateLayoutFromInstruction() {
  if (!state.current) return;
  const instruction = $("#layout-instruction").value.trim();
  if (!instruction) {
    showToast("请先描述资料怎样进入模板", true);
    return;
  }
  try {
    $("#generate-layout").disabled = true;
    const result = await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/layout-from-instruction", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({instruction: instruction, source_slide_index: sourceSlideIndex()})
    });
    state.current.layout_config = result.layout_config;
    state.current.project.layout_instruction = instruction;
    $("#layout-editor").value = pretty(result.layout_config);
    $("#layout-summary").textContent = mappingCount(result.layout_config) + " 组页面映射";
    renderPagePicker(state.current.template);
    await refreshLayoutPreview(result.layout_config);
    updateSteps();
    showToast("已生成映射，已在下方显示字段落点");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    $("#generate-layout").disabled = false;
  }
}

function setTab(name) {
  state.activeTab = name;
  $$(".tab").forEach(function (tab) { tab.classList.toggle("active", tab.dataset.tab === name); });
  $$(".panel").forEach(function (panel) { panel.classList.toggle("active", panel.id === "panel-" + name); });
}

function setDataView(name, sync) {
  if (!state.current) return;
  if (sync !== false && name === "buyer" && state.dataView === "json") {
    try {
      state.current.records = normalizeRecords(parseEditor("#records-editor", "数据"));
    } catch (error) {
      showToast(error.message, true);
      return;
    }
  }
  if (sync !== false && name === "json") $("#records-editor").value = pretty(state.current.project.mode === "buyer_briefing" ? currentBriefing() : currentRecords());
  state.dataView = name;
  $("#buyer-data-view").classList.toggle("hidden", name !== "buyer");
  const briefingView = $("#briefing-data-view");
  if (briefingView) briefingView.classList.toggle("hidden", name !== "briefing");
  $("#json-data-view").classList.toggle("hidden", name !== "json");
  $$("[data-data-view]").forEach(function (button) {
    button.classList.toggle("active", button.dataset.dataView === name);
  });
  if (name === "buyer") renderBuyerForm();
  if (name === "briefing") renderBriefingForm();
}

function researchJobText(job) {
  const report = job.report_data ? "\n结果：\n" + pretty(job.report_data) : "";
  const stderr = job.stderr ? "\n提示：\n" + job.stderr.trim() : "";
  return "任务 " + job.id + "\n阶段：" + (job.stage || job.status) + stderr + report;
}

async function pollResearch(jobId) {
  clearTimeout(state.researchTimer);
  try {
    const job = await api("/api/jobs/" + jobId);
    const box = $("#research-progress");
    box.className = "research-progress " + job.status;
    $("#research-status").textContent = job.stage || job.status;
    $("#research-log").textContent = researchJobText(job);
    if (job.status === "queued" || job.status === "running") {
      state.researchTimer = setTimeout(function () { pollResearch(jobId); }, 1000);
      return;
    }
    $("#run-research").disabled = false;
    if (job.status === "completed") {
      const count = job.report_data && Number(job.report_data.buyer_count || 0);
      if (!count) {
        showToast("搜索没有返回可回填买家，请调整筛选条件后重试", true);
        $("#research-progress").className = "research-progress failed";
        $("#research-status").textContent = "没有生成可回填买家";
        return;
      }
      await loadProject(job.project);
      $("#research-progress").className = "research-progress completed";
      $("#research-status").textContent = "搜索完成，已回填买家表单";
      $("#research-log").textContent = researchJobText(job);
      showToast("已生成 " + count + " 家买家资料");
    } else {
      showToast(job.stderr || "买家搜索失败", true);
    }
  } catch (error) {
    $("#run-research").disabled = false;
    showToast(error.message, true);
  }
}

async function runResearch() {
  if (!state.current) return;
  const country = $("#research-country").value.trim();
  const need = $("#research-need").value.trim();
  const count = Number($("#research-count").value || 10);
  if (!country || !need) {
    showToast("请同时填写国家和采购需求", true);
    return;
  }
  const settings = state.current.model_settings || {};
  if (settings.research_enabled === false) {
    showToast("当前是手动/导入资料模式，未启用买家资料生成模型。", true);
    return;
  }
  try {
    $("#run-research").disabled = true;
    $("#research-progress").className = "research-progress";
    $("#research-progress").classList.remove("hidden");
    $("#research-status").textContent = "正在启动买家搜索";
    $("#research-log").textContent = "将生成并整理企业名称、官网、具体采购产品和120-130字完整简介。";
    const job = await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/research-buyers", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        country: country,
        procurement_need: need,
        buyer_count: count,
        strategy: {
          preferred_industries: $("#preferred-industries").value.trim(),
          excluded_company_types: $("#excluded-company-types").value.trim(),
          custom_requirements: $("#custom-requirements").value.trim(),
          prefer_import_evidence: $("#prefer-import-evidence").checked,
          candidate_multiplier: Number($("#candidate-multiplier").value || 3)
        },
        fetch_assets: $("#fetch-assets").checked,
        enable_ai_visual_fallback: $("#fetch-assets").checked && $("#ai-visual-fallback").checked,
        asset_mode: "light"
      })
    });
    pollResearch(job.id);
  } catch (error) {
    $("#run-research").disabled = false;
    showToast(error.message, true);
  }
}

function updateModelSections() {
  const unified = $("#use-unified-model").checked;
  const anyEnabled = anyModelEnabled();
  $("#unified-model-fields").classList.toggle("hidden", !unified || !anyEnabled);
  $("#no-model-note").classList.toggle("hidden", anyEnabled);
  $$(".split-only").forEach(function (item) { item.classList.toggle("hidden", unified); });
  MODEL_ROLES.forEach(function (role) {
    const section = $('[data-role-section="' + role + '"]');
    if (section) section.classList.toggle("disabled", !roleEnabled(role));
  });
  if (!$("#fetch-assets").checked || !$("#enable-visual-model").checked) {
    $("#ai-visual-fallback").checked = false;
  }
  $("#ai-visual-fallback").disabled = !$("#fetch-assets").checked || !$("#enable-visual-model").checked;
}

async function openModelSettings() {
  try {
    const settings = await api("/api/model-settings");
    if (settings.providers) {
      Object.keys(MODEL_PROVIDER_DEFAULTS).forEach(function (key) { delete MODEL_PROVIDER_DEFAULTS[key]; });
      Object.assign(MODEL_PROVIDER_DEFAULTS, settings.providers);
    }
    populateProviderSelects();
    $("#enable-research-model").checked = settings.research_enabled !== false;
    $("#enable-visual-model").checked = Boolean(settings.visual_enabled);
    $("#enable-layout-model").checked = Boolean(settings.layout_enabled);
    $("#research-mode").value = settings.research_mode || "model_only";
    $("#use-unified-model").checked = Boolean(settings.unified);
    setSelectValue("#unified-provider", settings.unified_provider || "deepseek");
    setInputValue("#unified-base-url", settings.unified_base_url || providerDefaults(settings.unified_provider || "deepseek").base_url);
    MODEL_ROLES.forEach(function (role) {
      setSelectValue("#" + role + "-provider", settings[role + "_provider"] || "deepseek");
      setInputValue("#" + role + "-base-url", settings[role + "_base_url"] || providerDefaults(settings[role + "_provider"] || "deepseek").base_url);
      setInputValue("#" + role + "-model", settings[role + "_model"] || providerDefaults(settings[role + "_provider"] || "deepseek")[role + "_model"]);
      const keyInput = $("#" + role + "-api-key");
      if (keyInput) {
        keyInput.value = "";
        keyInput.placeholder = settings[role + "_configured"] ? "已配置，留空保持不变" : (role === "layout" ? "可留空" : "sk-...");
      }
      fillModelOptions(role, providerDefaults(settings[role + "_provider"] || "deepseek").models || []);
    });
    $("#unified-api-key").value = "";
    $("#unified-api-key").placeholder = settings.unified_configured ? "已配置，留空保持不变" : "sk-...";
    updateModelSections();
    $("#model-modal").classList.remove("hidden");
  } catch (error) {
    showToast(error.message, true);
  }
}

function closeModelSettings() {
  $("#model-modal").classList.add("hidden");
}

async function probeModelConnection(role) {
  const button = $('[data-probe-model="' + role + '"]');
  try {
    if (button) button.disabled = true;
    const payload = {role: role, provider: activeProvider(role), base_url: activeBaseUrl(role), api_key: activeApiKey(role)};
    const result = await api("/api/network-probe", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const parent = result.parent_process_probe || {};
    const child = result.child_process_probe || {};
    const summary = "\u6a21\u578b\u8fde\u63a5\u8bca\u65ad\n" +
      "\u670d\u52a1\u5546\uff1a" + (result.provider || "") + "\n" +
      "Base URL\uff1a" + (result.base_url || "") + "\n" +
      "Python\uff1a" + (result.python || "") + "\n" +
      "\u63a7\u5236\u53f0\u8fdb\u7a0b\uff1a" + (parent.reachable ? "\u53ef\u8fbe" : "\u4e0d\u53ef\u8fbe") + "\uff0cHTTP " + (parent.status || 0) + "\uff0c" + (parent.error || "\u65e0\u9519\u8bef") + "\n" +
      "\u641c\u7d22\u5b50\u8fdb\u7a0b\uff1a" + (child.reachable ? "\u53ef\u8fbe" : "\u4e0d\u53ef\u8fbe") + "\uff0cHTTP " + (child.status || 0) + "\uff0c" + (child.error || "\u65e0\u9519\u8bef") + "\n" +
      "\u8bf4\u660e\uff1aHTTP 401/403 \u4ee3\u8868\u7f51\u7edc\u53ef\u8fbe\uff0c\u53ea\u662f\u8bca\u65ad\u8bf7\u6c42\u672a\u643a\u5e26\u6b63\u5f0f\u9274\u6743\u3002";
    window.alert(summary);
    showToast(result.ok ? "\u8fde\u63a5\u8bca\u65ad\u5b8c\u6210\uff1a\u7f51\u7edc\u53ef\u8fbe" : "\u8fde\u63a5\u8bca\u65ad\u5b8c\u6210\uff1a\u7f51\u7edc\u4e0d\u53ef\u8fbe", !result.ok);
  } catch (error) {
    if (String(error.message || "").includes("\u63a5\u53e3\u4e0d\u5b58\u5728")) {
      window.alert("\u8bca\u65ad\u63a5\u53e3\u4e0d\u5b58\u5728\uff1a\u8bf4\u660e 5310 \u540e\u7aef\u8fd8\u662f\u65e7\u8fdb\u7a0b\uff0c\u8bf7\u5173\u95ed\u5f53\u524d\u63a7\u5236\u53f0\u670d\u52a1\u5e76\u91cd\u65b0\u542f\u52a8\u540e\u518d\u8bd5\u3002\u91cd\u542f\u540e /api/health \u5e94\u8be5\u663e\u793a version=3\u3002");
    }
    showToast(error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function fetchModelList(role) {
  const button = $('[data-fetch-models="' + role + '"]');
  if (!roleEnabled(role)) {
    showToast("该能力未启用，无需获取模型列表", true);
    return;
  }
  try {
    if (button) button.disabled = true;
    const payload = {role: role, provider: activeProvider(role), base_url: activeBaseUrl(role), api_key: activeApiKey(role)};
    const result = await api("/api/models", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    fillModelOptions(role, result.models || []);
    if (result.models && result.models.length && !$("#" + role + "-model").value.trim()) {
      $("#" + role + "-model").value = result.models[0];
    }
    showToast(result.ok ? "已获取上游模型列表" : "上游模型列表获取失败，已使用内置候选模型", false);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function saveModelSettings() {
  try {
    if ($("#enable-research-model").checked) syncProviderFromModel("research");
    const settings = await api("/api/model-settings", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        unified: $("#use-unified-model").checked,
        research_enabled: $("#enable-research-model").checked,
        research_mode: $("#research-mode").value,
        visual_enabled: $("#enable-visual-model").checked,
        layout_enabled: $("#enable-layout-model").checked,
        unified_provider: $("#unified-provider").value,
        unified_base_url: $("#unified-base-url").value,
        unified_key: $("#unified-api-key").value,
        research_provider: $("#research-provider").value,
        research_base_url: $("#research-base-url").value,
        research_key: $("#research-api-key").value,
        visual_provider: $("#visual-provider").value,
        visual_base_url: $("#visual-base-url").value,
        visual_key: $("#visual-api-key").value,
        layout_provider: $("#layout-provider").value,
        layout_base_url: $("#layout-base-url").value,
        layout_key: $("#layout-api-key").value,
        research_model: $("#research-model").value,
        visual_model: $("#visual-model").value,
        layout_model: $("#layout-model").value
      })
    });
    if (state.current) state.current.model_settings = settings;
    updateModelBadge();
    updateModelSections();
    closeModelSettings();
    showToast("模型设置已保存到当前控台会话");
  } catch (error) {
    showToast(error.message, true);
  }
}

function jobText(job) {
  const report = job.report_data ? "\n报告：\n" + pretty(job.report_data) : "";
  const stdout = job.stdout ? "\n输出：\n" + job.stdout.trim() : "";
  const stderr = job.stderr ? "\n错误：\n" + job.stderr.trim() : "";
  return "任务 " + job.id + "\n状态：" + (job.stage || job.status) + stdout + stderr + report;
}

async function pollJob(jobId) {
  clearTimeout(state.jobTimer);
  try {
    const job = await api("/api/jobs/" + jobId);
    const labels = {queued: "排队中", running: "生成中", completed: "已完成", failed: "失败"};
    $("#job-status").textContent = labels[job.status] || job.status;
    $("#job-status").className = "job-status " + job.status;
    $("#job-log").textContent = jobText(job);
    if (job.status === "queued" || job.status === "running") {
      state.jobTimer = setTimeout(function () { pollJob(jobId); }, 800);
      return;
    }
    $("#run-export").disabled = false;
    if (job.status === "completed") {
      showToast("PPTX 已生成");
      await loadProject(job.project);
    } else {
      showToast("导出失败，请查看运行日志", true);
    }
  } catch (error) {
    $("#run-export").disabled = false;
    showToast(error.message, true);
  }
}

function renderPreflight(result) {
  const host = $("#preflight-result");
  const errors = result.errors || [];
  const warnings = result.warnings || [];
  host.classList.remove("hidden");
  host.className = "preflight-result " + (result.ok ? "ready" : "failed");
  const summary = result.ok ? "检查通过：预计 " + result.expected_slide_count + " 页，" + result.record_count + " 条资料" : "检查发现 " + errors.length + " 个问题";
  host.innerHTML = '<strong>' + escapeHtml(summary) + '</strong>' +
    errors.map(function (item) { return '<span class="preflight-error">' + escapeHtml(item) + '</span>'; }).join("") +
    warnings.map(function (item) { return '<span class="preflight-warning">' + escapeHtml(item) + '</span>'; }).join("");
}

async function runPreflight() {
  if (!state.current) return null;
  try {
    const result = await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/preflight", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
    renderPreflight(result);
    if (!result.ok) showToast("请先处理生成前检查中的问题", true);
    else showToast("生成前检查通过");
    return result;
  } catch (error) { showToast(error.message, true); return null; }
}

async function runExport() {
  if (!state.current) return;
  try {
    if (state.dataView === "buyer") {
      await persistBuyerData(false);
    } else if (state.dataView === "briefing") {
      await persistBriefingData(false);
    } else {
      state.current.records = normalizeRecords(parseEditor("#records-editor", "数据"));
      await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/document/records", {
        method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(state.current.records)
      });
    }
    const layout = parseEditor("#layout-editor", "版式映射");
    await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/document/layout", {
      method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(layout)
    });
    state.current.layout_config = layout;
    const preflight = await runPreflight();
    if (!preflight || !preflight.ok) return;
    $("#run-export").disabled = true;
    $("#job-status").textContent = "准备中";
    $("#job-status").className = "job-status running";
    $("#job-log").textContent = "正在启动 PPTX 生成管线...";
    const job = await api("/api/projects/" + encodeURIComponent(state.current.project.slug) + "/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        filename: $("#output-filename").value,
        strict: $("#strict-mode").checked,
        presentation_engine: $("#presentation-engine").value
      })
    });
    pollJob(job.id);
  } catch (error) {
    $("#run-export").disabled = false;
    showToast(error.message, true);
  }
}

$("#new-project-form").addEventListener("submit", async function (event) {
  event.preventDefault();
  const input = $("#new-project-name");
  try {
    const project = await api("/api/projects", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: input.value, mode: $("#new-project-mode").value})
    });
    input.value = "";
    await refreshProjects(project.slug);
    showToast("项目已创建");
  } catch (error) {
    showToast(error.message, true);
  }
});

ensureConsoleEnhancements();
$("#refresh-projects").addEventListener("click", function () {
  refreshProjects().catch(function (error) { showToast(error.message, true); });
});
$("#template-file").addEventListener("change", function (event) { uploadTemplate(event.target.files[0]); });
$("#records-file").addEventListener("change", function (event) { importRecordsFile(event.target.files[0]); });
$("#import-pasted-text").addEventListener("click", function () { importPastedText().catch(function (error) { showToast(error.message, true); }); });
$("#save-records").addEventListener("click", function () { saveDocument("records"); });
$("#save-layout").addEventListener("click", function () { saveDocument("layout"); });
$("#generate-layout").addEventListener("click", generateLayoutFromInstruction);
$("#save-buyers").addEventListener("click", function () {
  persistBuyerData(true).catch(function (error) { showToast(error.message, true); });
});
$("#add-buyer").addEventListener("click", function () {
  currentRecords().records.push(blankBuyer($("#research-country").value.trim()));
  renderBuyerForm();
  updateSteps();
});
$("#run-research").addEventListener("click", runResearch);
$("#research-need").addEventListener("change", applyResearchDefaults);
$("#research-need").addEventListener("blur", applyResearchDefaults);
["#preferred-industries", "#excluded-company-types", "#custom-requirements"].forEach(function (selector) {
  $(selector).addEventListener("input", function () { this.dataset.autoDefault = ""; });
});
$("#run-export").addEventListener("click", runExport);
$("#run-preflight").addEventListener("click", runPreflight);
$("#refresh-layout-preview").addEventListener("click", function () {
  if (!state.current) return;
  try { refreshLayoutPreview(parseEditor("#layout-editor", "版式映射")); }
  catch (error) { showToast(error.message, true); }
});
$("#save-layout-recipe").addEventListener("click", saveLayoutRecipe);
$("#add-briefing-page").addEventListener("click", function () {
  currentBriefing().pages.push(blankBriefingPage());
  renderBriefingForm();
  updateSteps();
});
$("#save-briefing").addEventListener("click", function () {
  persistBriefingData(true).catch(function (error) { showToast(error.message, true); });
});
$$('[data-layout-example]').forEach(function (button) {
  button.addEventListener('click', function () {
    $('#layout-editor').value = pretty(layoutExample(button.dataset.layoutExample));
    showToast('\u5df2\u63d2\u5165\u793a\u4f8b\u6620\u5c04\uff0c\u8bf7\u6839\u636e\u6a21\u677f\u7ed3\u6784\u4fee\u6539 shape_index');
  });
});
$("#fetch-assets").addEventListener("change", function () {
  const visualEnabled = state.current && state.current.model_settings && state.current.model_settings.visual_enabled;
  $("#ai-visual-fallback").disabled = !$("#fetch-assets").checked || !visualEnabled;
  if ($("#ai-visual-fallback").disabled) $("#ai-visual-fallback").checked = false;
});
$("#ai-visual-fallback").disabled = true;
$$(".tab").forEach(function (tab) {
  tab.addEventListener("click", function () { setTab(tab.dataset.tab); });
});
$$("[data-data-view]").forEach(function (button) {
  button.addEventListener("click", function () { setDataView(button.dataset.dataView); });
});
$("#open-model-settings").addEventListener("click", openModelSettings);
$("#use-unified-model").addEventListener("change", updateModelSections);
["#enable-research-model", "#enable-visual-model", "#enable-layout-model"].forEach(function (selector) {
  $(selector).addEventListener("change", updateModelSections);
});
$$("[data-provider]").forEach(function (select) {
  select.addEventListener("change", function () { updateProviderDefaults(select.dataset.provider); });
});
$$("[data-fetch-models]").forEach(function (button) {
  button.addEventListener("click", function () { fetchModelList(button.dataset.fetchModels); });
});
$$("[data-probe-model]").forEach(function (button) {
  button.addEventListener("click", function () { probeModelConnection(button.dataset.probeModel); });
});
$("#save-model-settings").addEventListener("click", saveModelSettings);
$$("[data-close-model]").forEach(function (button) {
  button.addEventListener("click", closeModelSettings);
});
$$('[data-close-preview]').forEach(function (button) {
  button.addEventListener("click", closePreview);
});

refreshProjects().then(function () {
  if (state.projects.length) loadProject(state.projects[0].slug);
}).catch(function (error) { showToast(error.message, true); });
