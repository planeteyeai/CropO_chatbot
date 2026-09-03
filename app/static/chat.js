/**
 * AskO - Farmer & Plot-Scoped Chatbot Client with Multilingual Support (EN, HI, MR, KN).
 * Handles Plot Selection, On-demand Pre-fetching, and Multi-turn SSE Stream Consumption.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const plotModal = document.getElementById("plot-modal");
  const plotSelectForm = document.getElementById("plot-select-form");
  const plotIdInput = document.getElementById("plot-id-input");
  const languageSelect = document.getElementById("language-select");
  const headerLangSelect = document.getElementById("header-lang-select");
  const loadBtnText = document.getElementById("load-btn-text");
  const loadBtnSpinner = document.getElementById("load-btn-spinner");
  const switchPlotBtn = document.getElementById("switch-plot-btn");
  const headerSwitchBtn = document.getElementById("header-switch-btn");

  // Sidebar Elements
  const sidebarPlotBadge = document.getElementById("sidebar-plot-badge");
  const sidebarCropTitle = document.getElementById("sidebar-crop-title");
  const sidebarArea = document.getElementById("sidebar-area");
  const sidebarPlanted = document.getElementById("sidebar-planted");
  const sidebarIrrigation = document.getElementById("sidebar-irrigation");
  const refreshTelemetryBtn = document.getElementById("refresh-telemetry-btn");
  const statusSoilVal = document.getElementById("status-soil-val");
  const statusScoreVal = document.getElementById("status-score-val");
  const statusWeatherVal = document.getElementById("status-weather-val");

  // Chat Elements
  const headerPlotHeading = document.getElementById("header-plot-heading");
  const headerPlotSubheading = document.getElementById("header-plot-subheading");
  const welcomeMsgBody = document.getElementById("welcome-msg-body");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const messagesViewport = document.getElementById("messages-viewport");
  const quickPrompts = document.getElementById("quick-prompts");

  let currentPlotId = "";
  let currentLanguage = "en";
  let isStreaming = false;
  let lastPlotData = null;
  // Multi-turn conversation history buffer
  let conversationHistory = [];

  // Multilingual Translations Dictionary
  const TRANSLATIONS = {
    en: {
      botName: "AskO",
      welcomeTemplate: (id, cropType, variety, moisture, score) =>
        `Hello! I am AskO, your agronomic assistant for <strong>Plot #${id}</strong> (${cropType} - ${variety}).<br><br>` +
        `I have pre-fetched your plot's live crop metadata, weather, soil moisture (<strong>${moisture}%</strong>), and NDVI health score (<strong>${score}%</strong>) into the hot cache.<br><br>` +
        `Ask me anything about this plot or ask follow-up questions naturally!`,
      fallbackWelcome: (id) =>
        `Hello! I am AskO, your agronomic assistant for <strong>Plot #${id}</strong>.<br><br>` +
        `Your plot's crop metadata, soil moisture, NDVI health, and daily report are active in the hot cache.<br><br>` +
        `Ask me any questions about this plot!`,
      chips: [
        { label: "🥭 Crop & Variety Info", query: "What is the crop variety and plantation details for this plot?" },
        { label: "💧 Soil Moisture & Irrigation", query: "What is the current soil moisture and irrigation advisory for my plot?" },
        { label: "📊 Field Health Score", query: "What is the field health score and NDVI vigor for this plot?" },
        { label: "🛰️ 8 Satellite Layers", query: "Show me all 8 satellite layers data for this plot — growth, soil moisture, water uptake, pest, NPK, weather." },
        { label: "❓ What is NDVI?", query: "What is NDVI?" },
      ],
      inputPlaceholder: "Ask about this plot's soil moisture, irrigation needs, crop health, or weather...",
    },
    hi: {
      botName: "AskO",
      welcomeTemplate: (id, cropType, variety, moisture, score) =>
        `नमस्ते! मैं AskO हूँ — <strong>प्लाट #${id}</strong> (${cropType} - ${variety}) के लिए आपका कृषि सहायक।<br><br>` +
        `मैंने आपके खेत का फसल विवरण, मौसम, मिट्टी की नमी (<strong>${moisture}%</strong>), और NDVI फसल स्वास्थ्य स्कोर (<strong>${score}%</strong>) हॉट कैश में लोड कर लिया है।<br><br>` +
        `आप अपनी फसल या खेत के बारे में कुछ भी पूछ सकते हैं!`,
      fallbackWelcome: (id) =>
        `नमस्ते! मैं AskO हूँ — <strong>प्लाट #${id}</strong> के लिए आपका कृषि सहायक।<br><br>` +
        `आपके खेत का फसल विवरण, मिट्टी की नमी, स्वास्थ्य स्कोर और दैनिक रिपोर्ट हॉट कैश में सक्रिय हैं।<br><br>` +
        `आप अपने खेत के बारे में कोई भी प्रश्न पूछ सकते हैं!`,
      chips: [
        { label: "🥭 फसल और किस्म विवरण", query: "इस प्लॉट की फसल की किस्म और बुवाई का विवरण क्या है?" },
        { label: "💧 मिट्टी की नमी और सिंचाई सलाह", query: "मेरे प्लॉट के लिए वर्तमान मिट्टी की नमी और सिंचाई सलाह क्या है?" },
        { label: "📊 फसल स्वास्थ्य और NDVI स्कोर", query: "इस प्लॉट का फसल स्वास्थ्य स्कोर और NDVI स्तर क्या है?" },
        { label: "🌦️ मौसम और वर्षा पूर्वानुमान", query: "वर्तमान खेत का मौसम और बारिश का पूर्वानुमान क्या है?" },
        { label: "❓ अन्य प्रश्न (आउट-ऑफ-डोमेन)", query: "What is the stock price of Tesla?" },
      ],
      inputPlaceholder: "मिट्टी की नमी, सिंचाई, फसल स्वास्थ्य या मौसम के बारे में पूछें...",
    },
    mr: {
      botName: "AskO",
      welcomeTemplate: (id, cropType, variety, moisture, score) =>
        `नमस्कार! मी AskO आहे — <strong>प्लॉट #${id}</strong> (${cropType} - ${variety}) साठी आपला कृषी सहाय्यक.<br><br>` +
        `मी आपल्या शेताचा पीक तपशील, हवामान, जमिनीतील ओलावा (<strong>${moisture}%</strong>), आणि NDVI पीक आरोग्य स्कोअर (<strong>${score}%</strong>) हॉट कॅशमध्ये लोड केला आहे.<br><br>` +
        `आपल्या पिकाबद्दल किंवा शेतीबद्दल काहीही विचारा!`,
      fallbackWelcome: (id) =>
        `नमस्कार! मी AskO आहे — <strong>प्लॉट #${id}</strong> साठी आपला कृषी सहाय्यक.<br><br>` +
        `आपल्या शेताचा पीक तपशील, जमिनीतील ओलावा, आरोग्य स्कोअर आणि दैनिक अहवाल हॉट कॅशमध्ये उपलब्ध आहेत.<br><br>` +
        `आपल्या शेतीबद्दल कोणतेही प्रश्न विचारा!`,
      chips: [
        { label: "🥭 पीक व वाण माहिती", query: "या प्लॉटचा पीक प्रकार आणि लागवड तपशील काय आहे?" },
        { label: "💧 जमिनीतील ओलावा व सिंचन", query: "माझ्या प्लॉटमधील जमिनीतील ओलावा आणि सिंचन सल्ला काय आहे?" },
        { label: "📊 पीक आरोग्य स्कोअर", query: "या प्लॉटचा पीक आरोग्य स्कोअर आणि NDVI स्थिती काय आहे?" },
        { label: "🌦️ हवामान व पावसाचा अंदाज", query: "सध्याचे शेतातील हवामान आणि पावसाचा अंदाज काय आहे?" },
        { label: "❓ इतर प्रश्न (आउट-ऑफ-डोमेन)", query: "What is the stock price of Tesla?" },
      ],
      inputPlaceholder: "जमिनीतील ओलावा, सिंचन, पीक आरोग्य किंवा हवामानाबद्दल विचारा...",
    },
    kn: {
      botName: "AskO",
      welcomeTemplate: (id, cropType, variety, moisture, score) =>
        `ನಮಸ್ಕಾರ! ನಾನು AskO — ನಿಮ್ಮ <strong>ಪ್ಲಾಟ್ #${id}</strong> (${cropType} - ${variety}) ನ ಕೃಷಿ ಸಹಾಯಕ.<br><br>` +
        `ನಿಮ್ಮ ಜಮೀನಿನ ಬೆಳೆ ವಿವರ, ಹವಾಮಾನ, ಮಣ್ಣಿನ ತೇವಾಂಶ (<strong>${moisture}%</strong>), ಮತ್ತು NDVI ಬೆಳೆ ಆರೋಗ್ಯ ಸ್ಕೋರ್ (<strong>${score}%</strong>) ಅನ್ನು ಹಾಟ್ ಕ್ಯಾಶ್‌ನಲ್ಲಿ ಸಂಗ್ರಹಿಸಲಾಗಿದೆ.<br><br>` +
        `ನಿಮ್ಮ ಬೆಳೆ ಮತ್ತು ಜಮೀನಿನ ಬಗ್ಗೆ ಯಾವುದೇ ಪ್ರಶ್ನೆಗಳನ್ನು ಕೇಳಿ!`,
      fallbackWelcome: (id) =>
        `ನಮಸ್ಕಾರ! ನಾನು AskO — ನಿಮ್ಮ <strong>ಪ್ಲಾಟ್ #${id}</strong> ನ ಕೃಷಿ ಸಹಾಯಕ.<br><br>` +
        `ನಿಮ್ಮ ಜಮೀನಿನ ಬೆಳೆ ವಿವರ, ಮಣ್ಣಿನ ತೇವಾಂಶ, ಆರೋಗ್ಯ ಸ್ಕೋರ್ ಮತ್ತು ದೈನಂದಿನ ವರದಿ ಸಿದ್ಧವಾಗಿದೆ.<br><br>` +
        `ನಿಮ್ಮ ಜಮೀನಿನ ಬಗ್ಗೆ ಯಾವುದೇ ಪ್ರಶ್ನೆಗಳನ್ನು ಕೇಳಿ!`,
      chips: [
        { label: "🥭 ಬೆಳೆ ಮತ್ತು ತಳಿಯ ಮಾಹಿತಿ", query: "ಈ ಪ್ಲಾಟ್‌ನ ಬೆಳೆ ತಳಿ ಮತ್ತು ನಾಟಿ ವಿವರಗಳು ಯಾವುವು?" },
        { label: "💧 ಮಣ್ಣಿನ ತೇವಾಂಶ ಮತ್ತು ನೀರಾವರಿ", query: "ನನ್ನ ಪ್ಲಾಟ್‌ಗೆ ಪ್ರಸ್ತುತ ಮಣ್ಣಿನ ತೇವಾಂಶ ಮತ್ತು ನೀರಾವರಿ ಸಲಹೆ ಏನು?" },
        { label: "📊 ಬೆಳೆ ಆರೋಗ್ಯ ಸ್ಕೋರ್", query: "ಈ ಪ್ಲಾಟ್‌ನ ಬೆಳೆ ಆರೋಗ್ಯ ಸ್ಕೋರ್ ಮತ್ತು NDVI ಸ್ಥಿತಿ ಏನು?" },
        { label: "🌦️ ಹವಾಮಾನ ಮತ್ತು ಮಳೆಯ ಮುನ್ಸೂಚನೆ", query: "ಪ್ರಸ್ತುತ ಜಮೀನಿನ ಹವಾಮಾನ ಮತ್ತು ಮಳೆಯ ಮುನ್ಸೂಚನೆ ಏನು?" },
        { label: "❓ ಇತರ ಪ್ರಶ್ನೆ", query: "What is the stock price of Tesla?" },
      ],
      inputPlaceholder: "ಮಣ್ಣಿನ ತೇವಾಂಶ, ನೀರಾವರಿ, ಬೆಳೆ ಆರೋಗ್ಯ ಅಥವಾ ಹವಾಮಾನದ ಬಗ್ಗೆ ಕೇಳಿ...",
    },
  };

  // Helper to render quick prompts in the selected language
  function renderQuickPrompts(lang) {
    const config = TRANSLATIONS[lang] || TRANSLATIONS.en;
    if (quickPrompts) {
      quickPrompts.innerHTML = config.chips
        .map((c) => `<button class="chip" data-query="${escapeHtml(c.query)}">${escapeHtml(c.label)}</button>`)
        .join("");
    }
    if (chatInput) {
      chatInput.placeholder = config.inputPlaceholder;
    }
  }

  // Set Language Handler
  function setLanguage(lang) {
    const validLang = TRANSLATIONS[lang] ? lang : "en";
    currentLanguage = validLang;
    if (languageSelect) languageSelect.value = validLang;
    if (headerLangSelect) headerLangSelect.value = validLang;

    renderQuickPrompts(validLang);

    // If a plot is already loaded, refresh the welcome message to the new language
    if (currentPlotId && lastPlotData) {
      renderWelcomeMessage(currentPlotId, lastPlotData, validLang);
    }
  }

  // Helper to render localized welcome message
  function renderWelcomeMessage(cleanId, data, lang) {
    const t = TRANSLATIONS[lang] || TRANSLATIONS.en;
    const info = data.info || {};
    const crop = info.crop_details || {};
    const soil = data.soil || {};
    const score = data.score || {};

    const cropType = crop.crop_type || "Crop";
    const cropVariety = crop.crop_variety || "Standard";
    const moisture = soil.latest_moisture_pct || 80;
    const healthScore = score.field_score_pct || 100;

    messagesViewport.innerHTML = `
      <div class="message assistant-msg">
        <div class="msg-avatar">🤖</div>
        <div class="msg-content">
          <div class="msg-header">${t.botName} (Plot #${cleanId})</div>
          <div class="msg-body" id="welcome-msg-body">
            ${t.welcomeTemplate(cleanId, cropType, cropVariety, moisture, healthScore)}
          </div>
        </div>
      </div>
    `;
  }

  // 1. Pre-fetch and activate telemetry for a specific plot (triggered on user submit)
  async function activatePlot(plotId, options = {}) {
    const { clearCache = false } = options;
    const cleanId = String(plotId).trim();
    if (!cleanId) return;

    loadBtnText.textContent = clearCache
      ? `Refreshing Plot #${cleanId}...`
      : `Loading Plot #${cleanId}...`;
    loadBtnSpinner.classList.remove("hidden");

    const endpoint = clearCache ? "/api/plots/refresh" : "/api/plots/load";

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plot_id: cleanId }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      currentPlotId = cleanId;
      lastPlotData = data;
      // Reset conversation history for new plot session
      conversationHistory = [];

      // Update UI with plot telemetry
      const info = data.info || {};
      const crop = info.crop_details || {};
      const soil = data.soil || {};
      const score = data.score || {};
      const weather = data.weather || {};

      const cropType = crop.crop_type || "Active Cultivation";
      const cropVariety = crop.crop_variety || "Standard";
      const area = info.area_acres || 1.0;
      const planted = crop.plantation_date || "N/A";
      const irrigation = crop.irrigation_type || "Drip Irrigation";

      // Update Sidebar
      sidebarPlotBadge.textContent = `Plot #${cleanId}`;
      sidebarCropTitle.textContent = `${cropType} (${cropVariety})`;
      sidebarArea.textContent = `${area} acres`;
      sidebarPlanted.textContent = planted;
      sidebarIrrigation.textContent = irrigation;
      switchPlotBtn.textContent = "Switch";

      // Update Status Pills
      statusSoilVal.textContent = `${soil.latest_moisture_pct || 80}% (${soil.moisture_status || "Normal"})`;
      statusScoreVal.textContent = `${score.field_score_pct || 100}% (${score.health_status || "Vigor"})`;
      const curWeather = weather.current || {};
      statusWeatherVal.textContent = `${curWeather.temperature_celsius || 24.5}°C (${curWeather.rain_status || "Clear"})`;

      // Update Header
      headerPlotHeading.textContent = `AskO — Plot #${cleanId}`;
      headerPlotSubheading.textContent = `Live insights grounded in pre-fetched telemetry for ${cropType} (${cropVariety}) orchard.`;

      // Render welcome message in current selected language
      renderWelcomeMessage(cleanId, data, currentLanguage);

      // Hide Modal
      plotModal.classList.add("hidden");
    } catch (err) {
      console.warn("Plot telemetry pre-fetch fallback:", err);
      currentPlotId = cleanId;
      lastPlotData = {};
      conversationHistory = [];

      // Set fallback sidebar & header values
      sidebarPlotBadge.textContent = `Plot #${cleanId}`;
      sidebarCropTitle.textContent = `Plot #${cleanId} (Active)`;
      sidebarArea.textContent = `1.0 acres`;
      sidebarPlanted.textContent = `N/A`;
      sidebarIrrigation.textContent = `Drip Irrigation`;
      switchPlotBtn.textContent = "Switch";
      statusSoilVal.textContent = `81.4% (Hydrated)`;
      statusScoreVal.textContent = `100% (Vigor)`;
      statusWeatherVal.textContent = `24.5°C (Stable)`;

      headerPlotHeading.textContent = `AskO — Plot #${cleanId}`;
      headerPlotSubheading.textContent = `Active session for Plot #${cleanId}.`;

      const t = TRANSLATIONS[currentLanguage] || TRANSLATIONS.en;
      messagesViewport.innerHTML = `
        <div class="message assistant-msg">
          <div class="msg-avatar">🤖</div>
          <div class="msg-content">
            <div class="msg-header">${t.botName} (Plot #${cleanId})</div>
            <div class="msg-body" id="welcome-msg-body">
              ${t.fallbackWelcome(cleanId)}
            </div>
          </div>
        </div>
      `;

      plotModal.classList.add("hidden");
    } finally {
      loadBtnText.textContent = "Connect & Load Telemetry";
      loadBtnSpinner.classList.add("hidden");
    }
  }

  // 2. Handle Form Submit for Plot Selection & Language
  plotSelectForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const enteredId = plotIdInput.value.trim();
    if (languageSelect) {
      setLanguage(languageSelect.value);
    }
    if (enteredId) {
      activatePlot(enteredId);
    }
  });

  // Language Dropdown Event Listeners
  if (languageSelect) {
    languageSelect.addEventListener("change", (e) => {
      setLanguage(e.target.value);
    });
  }

  if (headerLangSelect) {
    headerLangSelect.addEventListener("change", (e) => {
      setLanguage(e.target.value);
    });
  }

  // Switch Plot modal triggers
  function showPlotModal() {
    if (plotIdInput) {
      plotIdInput.value = currentPlotId || "";
      setTimeout(() => plotIdInput.focus(), 60);
    }
    if (languageSelect) {
      languageSelect.value = currentLanguage;
    }
    plotModal.classList.remove("hidden");
  }

  switchPlotBtn.addEventListener("click", showPlotModal);
  headerSwitchBtn.addEventListener("click", showPlotModal);
  refreshTelemetryBtn.addEventListener("click", () => {
    if (currentPlotId) {
      activatePlot(currentPlotId, { clearCache: true });
    } else {
      showPlotModal();
    }
  });

  // Initialize Language and Quick Prompts on startup
  setLanguage("en");

  // Always show modal on startup to prompt user for Plot ID
  showPlotModal();

  // 3. Simple Markdown formatter
  function formatMarkdown(text) {
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(?:^|\n)[*-] (.*?)(?=\n|$)/g, "<br>• $1");
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function scrollToBottom() {
    messagesViewport.scrollTop = messagesViewport.scrollHeight;
  }

  function appendUserMessage(text) {
    const msgDiv = document.createElement("div");
    msgDiv.className = "message user-msg";
    msgDiv.innerHTML = `
      <div class="msg-avatar">👤</div>
      <div class="msg-content">
        <div class="msg-header">You</div>
        <div class="msg-body">${formatMarkdown(text)}</div>
      </div>
    `;
    messagesViewport.appendChild(msgDiv);
    scrollToBottom();
  }

  function createAssistantMessageBubble() {
    const t = TRANSLATIONS[currentLanguage] || TRANSLATIONS.en;
    const msgDiv = document.createElement("div");
    msgDiv.className = "message assistant-msg";
    msgDiv.innerHTML = `
      <div class="msg-avatar">🤖</div>
      <div class="msg-content">
        <div class="msg-header">${t.botName} (Plot #${currentPlotId || "1"})</div>
        <div class="msg-body"><span class="typing-cursor"></span></div>
      </div>
    `;
    messagesViewport.appendChild(msgDiv);
    scrollToBottom();
    return msgDiv.querySelector(".msg-body");
  }

  // 4. Send Query to /chat with SSE stream rendering & conversation history & language
  async function handleSendQuery(queryText) {
    const query = queryText.trim();
    if (!query || isStreaming) return;

    if (!currentPlotId) {
      showPlotModal();
      return;
    }

    appendUserMessage(query);
    chatInput.value = "";
    chatInput.disabled = true;
    sendBtn.disabled = true;
    isStreaming = true;

    // Snapshot current history before this message
    const previousHistory = [...conversationHistory];
    // Record user message in history
    conversationHistory.push({ role: "user", content: query });

    const assistantBody = createAssistantMessageBubble();
    let accumulatedText = "";

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          plot_id: currentPlotId,
          message: query,
          history: previousHistory,
          language: currentLanguage,
          session_id: `plot-${currentPlotId}`,
        }),
      });

      if (!response.ok) {
        throw new Error(`Server error: HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const block of lines) {
          const trimmed = block.trim();
          if (!trimmed.startsWith("data:")) continue;

          const jsonStr = trimmed.replace(/^data:\s*/, "");
          try {
            const data = JSON.parse(jsonStr);
            if (data.token) {
              accumulatedText += data.token;
              assistantBody.innerHTML =
                formatMarkdown(accumulatedText) +
                '<span class="typing-cursor"></span>';
              scrollToBottom();
            }
            if (data.done) {
              assistantBody.innerHTML = formatMarkdown(accumulatedText);
              scrollToBottom();
            }
          } catch (e) {
            console.error("SSE parse error:", e);
          }
        }
      }

      assistantBody.innerHTML = formatMarkdown(accumulatedText);
      // Append completed assistant answer to history
      if (accumulatedText) {
        conversationHistory.push({ role: "assistant", content: accumulatedText });
      }
    } catch (err) {
      console.error("Chat streaming error:", err);
      assistantBody.innerHTML = `<span style="color: var(--accent-red)">⚠️ Error: ${escapeHtml(
        err.message
      )}</span>`;
    } finally {
      isStreaming = false;
      chatInput.disabled = false;
      sendBtn.disabled = false;
      chatInput.focus();
      scrollToBottom();
    }
  }

  // Bind Form Submit
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleSendQuery(chatInput.value);
  });

  // Bind Quick Suggestion Chips
  if (quickPrompts) {
    quickPrompts.addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (chip && chip.dataset.query) {
        handleSendQuery(chip.dataset.query);
      }
    });
  }
});
