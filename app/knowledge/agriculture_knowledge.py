"""Offline agricultural knowledge snippets used when FAQ is close but not exact."""

from typing import Any, Dict, Optional

KNOWLEDGE: Dict[str, Dict[str, str]] = {
    "fusion": {
        "en": (
            "Answer as satellite + AI in short bullets. Use cached plot numbers as evidence only. "
            "Answer this question only. Never start with 'Based on the satellite'. Never recap layers."
        ),
        "hi": "केवल सैटेलाइट न पढ़ें। कैश संख्या + फसल/अवस्था/मौसम मिलाकर सलाह दें। 'सैटेलाइट के अनुसार' से शुरू न करें।",
        "mr": "फक्त सॅटेलाइट वाचू नका. कॅश आकडे + पीक/अवस्था/हवामान मिळवून सल्ला द्या. 'सॅटेलाइटनुसार' ने सुरू करू नका.",
        "kn": "ಕೇವಲ ಉಪಗ್ರಹ ಓದಬೇಡಿ. ಸಂಖ್ಯೆ + ಬೆಳೆ/ಹಂತ/ಹವಾಮಾನ ಸೇರಿಸಿ ಸಲಹೆ. 'ಉಪಗ್ರಹದ ಪ್ರಕಾರ' ಎಂದು ಪ್ರಾರಂಭಿಸಬೇಡಿ.",
    },
    "ndvi": {
        "en": "NDVI (Normalized Difference Vegetation Index) estimates canopy greenness from satellite. Higher NDVI usually means denser, healthier vegetation — it is not a direct yield guarantee.",
        "hi": "NDVI उपग्रह से फसल की हरियाली मापता है। अधिक NDVI आमतौर पर स्वस्थ पत्ती घनत्व दर्शाता है।",
        "mr": "NDVI उपग्रहाद्वारे पिकाची हिरवळ मोजते. जास्त NDVI सामान्यतः चांगले पीक जोम दर्शवते.",
        "kn": "NDVI ಉಪಗ್ರಹದಿಂದ ಬೆಳೆಯ ಹಸಿರುತನವನ್ನು ಅಳೆಯುತ್ತದೆ. ಹೆಚ್ಚಿನ NDVI ಸಾಮಾನ್ಯವಾಗಿ ಉತ್ತಮ ಬೆಳೆ ಆರೋಗ್ಯವನ್ನು ಸೂಚಿಸುತ್ತದೆ.",
    },
    "soil_moisture": {
        "en": "Soil moisture is the water held in the root zone. Irrigation decisions should combine moisture, crop stage, recent rain, forecast, and evapotranspiration — not moisture alone.",
        "hi": "मिट्टी की नमी जड़ क्षेत्र में पानी है। सिंचाई नमी, फसल अवस्था, बारिश और पूर्वानुमान को साथ देखकर तय करें।",
        "mr": "जमिनीतील ओलावा मुळांच्या भागातील पाणी आहे. सिंचन ओलावा, पाऊस आणि हवामान अंदाज एकत्र पाहून ठरवावे.",
        "kn": "ಮಣ್ಣಿನ ತೇವಾಂಶ ಬೇರಿನ ವಲಯದ ನೀರು. ನೀರಾವರಿ ನಿರ್ಧಾರಕ್ಕೆ ತೇವಾಂಶ, ಮಳೆ ಮತ್ತು ಮುನ್ಸೂಚನೆಯನ್ನು ಒಟ್ಟಿಗೆ ನೋಡಿ.",
    },
    "drip": {
        "en": "Drip irrigation delivers water near the root zone. Pause or shorten cycles when soil is already saturated or rain is likely, to protect roots and save water.",
        "hi": "ड्रिप सिंचाई जड़ों के पास पानी देती है। मिट्टी पहले से गीली हो या बारिश आने वाली हो तो चक्र रोकें या छोटा करें।",
        "mr": "ठिबक सिंचन मुळांजवळ पाणी देते. जमीन संतृप्त असेल किंवा पाऊस येणार असेल तर चक्र थांबवा किंवा कमी करा.",
        "kn": "ಹನಿ ನೀರಾವರಿ ಬೇರಿನ ಬಳಿ ನೀರು ನೀಡುತ್ತದೆ. ಮಣ್ಣು ತುಂಬಾ ತೇವವಾಗಿದ್ದರೆ ಅಥವಾ ಮಳೆ ಬರುವ ಸಾಧ್ಯತೆ ಇದ್ದರೆ ಚಕ್ರವನ್ನು ನಿಲ್ಲಿಸಿ.",
    },
    "pest": {
        "en": "If the farmer asks what to do about pests, name IPM steps: scout flagged patches, pheromone traps for borers, Trichogramma if available, hand-pick larvae, remove infested shoots, neem/azadirachtin only after live pests are seen (labelled rate). Quote pest-affected acres, not pixels. Do not write a satellite disclaimer as the whole answer.",
        "hi": "कीट पर: प्रभावित भाग जाँचें, फेरोमोन ट्रैप, ट्राइकोग्रामा, इल्ली हाथ से निकालें, संक्रमित कल्ले हटाएँ, पुष्टि के बाद नीम (लेबल दर)। पूरे उत्तर में सैटेलाइट डिस्क्लेमर न लिखें।",
        "mr": "कीड: खूण केलेले भाग तपासा, फेरोमोन सापळे, ट्रायकोग्रामा, अळ्या हाताने काढा, संक्रमित फुटे काढा, पुष्टीनंतर नीम. संपूर्ण उत्तरात सॅटेलाइट डिस्क्लेमर लिहू नका.",
        "kn": "ಕೀಟ: ಗುರುತು ಭಾಗ ನೋಡಿ, ಫೆರೊಮೋನ್ ಬಲೆ, ಟ್ರೈಕೋಗ್ರಾಮಾ, ಹುಳು ತೆಗೆಯಿರಿ, ಬೇವು ಲೇಬಲ್ ಪ್ರಮಾಣ. ಉತ್ತರವನ್ನು ಸ್ಯಾಟಲೈಟ್ ಡಿಸ್ಕ್ಲೇಮರ್ ಮಾಡಬೇಡಿ.",
    },
    "pest_identity": {
        "en": (
            "Fuse satellite class + crop + growth stage + weather (cached AND any weather the farmer stated). "
            "Satellite chewing/fungi/sucking is a class, not a lab ID — still PREDICT likely names. Never reply only that satellite cannot identify the pest. "
            "Sugarcane chewing (humid/rain, ~80% RH): internodal/stem borer (Chilo sacchariphagus), top shoot borer (Scirpophaga excerptalis), "
            "leaf-eating armyworm/caterpillars after rains; early shoot borer (Chilo infuscatellus) if the crop is young/tillering. "
            "White grub after monsoon rains if damage is at the base. Pyrilla is sucking, not chewing. "
            "Say 'most likely / predicted' and quote affected acres (never pixels), then scout to confirm. Name 2–3 species."
        ),
        "hi": "सैटेलाइट वर्ग + फसल + अवस्था + मौसम मिलाकर संभावित कीट नाम बताएँ। केवल 'पहचान नहीं हो सकती' न कहें। गन्ने में नमी/बारिश पर इंटरनोड/टॉप बोरर, आर्मीवर्म; युवा फसल पर अर्ली शूट बोरर। भविष्यवाणी कहें, स्काउटिंग से पुष्टि करें।",
        "mr": "सॅटेलाइट वर्ग + पीक + अवस्था + हवामान मिळवून संभाव्य कीड नावे सांगा. फक्त 'ओळखता येत नाही' म्हणू नका. ऊस: आर्द्र/पावसात स्टेम/टॉप बोरर, आर्मीवर्म. अंदाज सांगा, शेतात तपासा.",
        "kn": "ಉಪಗ್ರಹ ವರ್ಗ + ಬೆಳೆ + ಹಂತ + ಹವಾಮಾನ ಸೇರಿಸಿ ಸಂಭವನೀಯ ಕೀಟ ಹೆಸರು. 'ಗುರುತಿಸಲಾಗದು' ಮಾತ್ರ ಹೇಳಬೇಡಿ. ಕಬ್ಬು ತೇವ/ಮಳೆ: ಕಾಂಡ/ಟಾಪ್ ಬೋರರ್, ಆರ್ಮಿವರ್ಮ್.",
    },
    "npk": {
        "en": (
            "When NPK kg/acre is in the evidence, name the common fertilizers that supply it: "
            "Urea (46% N), DAP (18-46-0) or SSP for phosphorus, and MOP/SOP for potassium. "
            "List them under heading Chemical. Pair with heading Organic from ORGANIC FOR THIS FIELD. "
            "Split nitrogen in 2–3 applications for sugarcane. Subtract fertilizer already applied. Confirm with a soil test."
        ),
        "hi": "NPK से यूरिया (46% N), DAP, और MOP निकालें। THIS FIELD doses पंक्ति की मात्रा इस खेत के एकड़ पर बताएँ (किग्रा/एकड़ कोष्ठक में)। नाइट्रोजन बाँटकर दें। मिट्टी परीक्षण से पुष्टि करें।",
        "mr": "NPK वरून युरिया, DAP आणि MOP सांगा. THIS FIELD doses ओळीतील प्रमाण या शेताच्या एकरासाठी सांगा (किग्रॅ/एकर कंसात). नायट्रोजन विभागून द्या. माती परीक्षण करा.",
        "kn": "NPK ನಿಂದ ಯೂರಿಯಾ, DAP, MOP ಹೆಸರಿಸಿ. THIS FIELD doses ಸಾಲಿನ ಪ್ರಮಾಣ ಈ ಜಮೀನಿನ ಎಕರೆಗೆ ಹೇಳಿ (ಕೆಜಿ/ಎಕರೆ ಆವರಣದಲ್ಲಿ). ಸಾರಜನಕವನ್ನು ಹಂಚಿ ಹಾಕಿ. ಮಣ್ಣು ಪರೀಕ್ಷೆ ಮಾಡಿ.",
    },
    "nutrition_and_pests": {
        "en": (
            "No fertilizer kills pests by itself. Still recommend the NPK fertilizers from cache, plus prevention: "
            "do not over-apply nitrogen (soft tissue attracts sucking pests); keep potassium (MOP) as recommended for stronger canes; "
            "neem cake as an organic soil amendment at a labelled/local agri rate; "
            "weekly scouting, borer pheromone traps, Trichogramma if available, remove infested shoots. "
            "Spray neem/azadirachtin only after live pests are confirmed. Never invent a brand or ml/acre."
        ),
        "hi": "खाद कीट नहीं मारती। फिर भी NPK खाद बताएँ, पोटाश बनाए रखें, अधिक नाइट्रोजन न डालें, नीम खली (लेबल दर), स्काउटिंग, फेरोमोन ट्रैप, ट्राइकोग्रामा, संक्रमित कल्ले हटाएँ।",
        "mr": "खत कीड मारत नाही. तरी NPK खते सांगा, पोटॅश ठेवा, जास्त नायट्रोजन टाळा, कडुलिंब पेंड, स्काउटिंग, फेरोमोन सापळे, ट्रायकोग्रामा.",
        "kn": "ಗೊಬ್ಬರ ಕೀಟವನ್ನು ಕೊಲ್ಲುವುದಿಲ್ಲ. ಆದರೆ NPK ಗೊಬ್ಬರ ಹೇಳಿ, ಪೊಟ್ಯಾಸಿಯಮ್ ಇರಲಿ, ಹೆಚ್ಚು ಸಾರಜನಕ ಬೇಡ, ಬೇವಿನ ಹಿಂಡಿ, ಸ್ಕೌಟಿಂಗ್, ಫೆರೊಮೋನ್ ಬಲೆ, ಟ್ರೈಕೋಗ್ರಾಮಾ.",
    },
    "organic_fertilizer": {
        "en": (
            "Always classify the answer as Chemical vs Organic, scaled to THIS field's acres. "
            "Chemical: Urea/DAP/MOP from THIS FIELD doses. "
            "Organic: use ORGANIC FOR THIS FIELD tonnes when present (FYM/compost and vermicompost); "
            "add rock phosphate, neem cake, Jeevamrut in one short line. No brands."
        ),
        "hi": "रासायनिक NPK के साथ जैविक विकल्प भी दें: गोबर खाद/कम्पोस्ट 2–5 टन/एकड़, वर्मीकम्पोस्ट 1–1.5 टन/एकड़, रॉक फॉस्फेट, राख/पोटाश कम्पोस्ट, नीम खली (लेबल दर), जीवामृत। जैविक धीमा है पर मिट्टी कार्बन बढ़ाता है।",
        "mr": "रासायनिक NPK सोबत सेंद्रिय पर्याय: शेणखत/कंपोस्ट 2–5 टन/एकर, वर्मीकंपोस्ट, रॉक फॉस्फेट, राख, कडुलिंब पेंड, जीवामृत. सेंद्रिय हळू पण मातीतील कार्बन वाढवते.",
        "kn": "ರಾಸಾಯನಿಕ NPK ಜೊತೆ ಸಾವಯವ: FYM/ಕಾಂಪೋಸ್ಟ್, ವರ್ಮಿಕಾಂಪೋಸ್ಟ್, ರಾಕ್ ಫಾಸ್ಫೇಟ್, ಬೂದಿ, ಬೇವಿನ ಹಿಂಡಿ, ಜೀವಾಮೃತ. ಸಾವಯವ ನಿಧಾನ, ಮಣ್ಣಿನ ಇಂಗಾಲ ಹೆಚ್ಚಿಸುತ್ತದೆ.",
    },
    "carbon_practices": {
        "en": (
            "Carbon-credit practices: the CropO app's in-app credit estimate is for rice AWD (alternate wetting and drying) "
            "to cut methane — do not invent a ₹/credit figure for other crops. "
            "Still recommend soil-carbon practices that help yield and future carbon programs: "
            "FYM/compost and trash mulching, avoid burning residue, don't over-apply nitrogen, "
            "drip instead of flood where possible, keep a green cover or intercrop if the crop allows. "
            "Say these raise soil organic carbon and may support later carbon projects; they are not a certified credit by themselves."
        ),
        "hi": "कार्बन क्रेडिट अनुमान ऐप में धान AWD (मीथेन) के लिए है — अन्य फसल पर ₹/क्रेडिट न गढ़ें। फिर भी गोबर खाद, कचरा मल्च, अवशेष न जलाएँ, अधिक नाइट्रोजन न डालें, ड्रिप — ये मिट्टी कार्बन बढ़ाते हैं।",
        "mr": "कार्बन क्रेडिट अंदाज अॅपमध्ये भात AWD साठी आहे. इतर पिकावर ₹/क्रेडिट काढू नका. शेणखत, आच्छादन, अवशेष जाळू नका, जास्त नायट्रोजन टाळा, ठिबक — माती कार्बन वाढते.",
        "kn": "ಕಾರ್ಬನ್ ಕ್ರೆಡಿಟ್ ಅಂದಾಜು ಅಪ್‌ನಲ್ಲಿ ಭತ್ತ AWD. ಇತರ ಬೆಳೆಗೆ ₹ ಕಲ್ಪಿಸಬೇಡಿ. FYM, ಹೊದಿಕೆ, ಉಳಿಕೆ ಸುಡಬೇಡಿ, ಹೆಚ್ಚು ಸಾರಜನಕ ಬೇಡ, ಹನಿ ನೀರಾವರಿ.",
    },
    "yield_sanity": {
        "en": (
            "Never quote raw max_yield as tonnes/acre if it is above ~120 for sugarcane. "
            "Use the INTERPRETED YIELD line. Maharashtra sugarcane is typically 28–40 t/acre; "
            "good 40–60; exceptional 80–100. 443 t/acre is not realistic. "
            "If the farmer asks 'is this realistic', answer that first: the interpreted tonnes/acre "
            "and total tonnes for this plot size, then that it is tentative."
        ),
        "hi": "गन्ने पर कच्चा max_yield 120 टन/एकड़ से ऊपर मत बताएँ। व्याख्या वाली उपज पंक्ति इस्तेमाल करें। महाराष्ट्र में आमतौर पर 28–40 टन/एकड़। 443 टन/एकड़ वास्तविक नहीं।",
        "mr": "ऊसासाठी कच्चा max_yield 120 टन/एकर समजू नका. INTERPRETED YIELD वापरा. महाराष्ट्रात साधारण 28–40 टन/एकर. 443 टन/एकर वास्तव नाही.",
        "kn": "ಕಬ್ಬಿಗೆ ಕಚ್ಚಾ max_yield ಅನ್ನು 120 t/acre ಎಂದು ಹೇಳಬೇಡಿ. INTERPRETED YIELD ಬಳಸಿ. 443 t/acre ವಾಸ್ತವಿಕವಲ್ಲ.",
    },
    "organic_ipm": {
        "en": (
            "Standard organic / IPM practices for chewing pests (borers, caterpillars, beetles) on sugarcane and similar field crops: "
            "(1) Scout flagged patches weekly; collect egg masses and larvae by hand when counts are low. "
            "(2) Pheromone traps for stem borers for early monitoring. "
            "(3) Release Trichogramma egg parasitoids where locally available. "
            "(4) Neem / azadirachtin on an organic-approved labelled product after live pests are confirmed — do not invent a dose or brand. "
            "(5) Crop hygiene: remove infested shoots and trash so borers cannot carry over. "
            "(6) Conserve beneficial insects — skip broad-spectrum insecticide at low satellite flags. "
            "At a low satellite pest flag, start with scouting + traps/biocontrol; spray only if field counts confirm an economic infestation."
        ),
        "hi": "जैविक/IPM: प्रभावित हिस्से की जाँच, इल्ली/अंडे हाथ से निकालना, तना छेदक के लिए फेरोमोन ट्रैप, उपलब्ध हो तो ट्राइकोग्रामा, पुष्टि के बाद नीम/एजाडिरेक्टिन (लेबल दर), संक्रमित कल्ले हटाना, कम संकेत पर व्यापक कीटनाशक न डालें। मात्रा या ब्रांड न गढ़ें।",
        "mr": "सेंद्रिय/IPM: खूण केलेले भाग तपासा, अळ्या/अंडी हाताने काढा, खोडकिडा फेरोमोन सापळे, उपलब्ध असेल तर ट्रायकोग्रामा, पुष्टीनंतर नीम (लेबल प्रमाण), संक्रमित फुटे काढा, कमी संकेतावर व्यापक कीटकनाशक वापरू नका. डोस/ब्रँड तयार करू नका.",
        "kn": "ಸಾವಯವ/IPM: ಗುರುತು ಮಾಡಿದ ಭಾಗ ನೋಡಿ, ಹುಳು/ಮೊಟ್ಟೆ ಕೈಯಿಂದ ತೆಗೆಯಿರಿ, ಕಾಂಡ ಕೊರಕ ಫೆರೊಮೋನ್ ಬಲೆ, ಲಭ್ಯವಿದ್ದರೆ ಟ್ರೈಕೋಗ್ರಾಮಾ, ದೃಢಪಟ್ಟ ನಂತರ ಬೇವು (ಲೇಬಲ್ ಪ್ರಮಾಣ). ಕಡಿಮೆ ಸಂಕೇತದಲ್ಲಿ ವ್ಯಾಪಕ ಕೀಟನಾಶಕ ಬೇಡ. ಡೋಸ್/ಬ್ರಾಂಡ್ ಕಲ್ಪಿಸಬೇಡಿ.",
    },
}


def lookup_knowledge(topic: str, language: str = "en") -> str:
    pack = KNOWLEDGE.get(topic) or {}
    return pack.get(language) or pack.get("en") or ""


def npk_to_common_fertilizers(n: Any, p: Any, k: Any) -> Optional[Dict[str, float]]:
    """Convert N-P-K kg/acre into urea, DAP, and MOP using standard nutrient grades."""
    try:
        n_v = float(n)
        p_v = float(p)
        k_v = float(k)
    except (TypeError, ValueError):
        return None
    if n_v < 0 or p_v < 0 or k_v < 0:
        return None
    dap = round(p_v / 0.46, 1) if p_v else 0.0
    n_from_dap = round(dap * 0.18, 1)
    n_left = max(n_v - n_from_dap, 0.0)
    urea = round(n_left / 0.46, 1) if n_left else 0.0
    mop = round(k_v / 0.60, 1) if k_v else 0.0
    return {
        "n_kg": round(n_v, 2),
        "p_kg": round(p_v, 2),
        "k_kg": round(k_v, 2),
        "urea_kg": urea,
        "dap_kg": dap,
        "mop_kg": mop,
    }
