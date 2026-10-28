"use strict";
const recordButton = document.querySelector("#record");
const discardButton = document.querySelector("#discard-audio");
const voiceStatus = document.querySelector("#voice-status");
const speakToggle = document.querySelector("#speak");
const stopSpeech = document.querySelector("#stop-speech");
let recorder = null, microphone = null, timer = null, recording = false, acquiring = false;
let cancelled = false, chunks = [], audioSize = 0;
const maxBytes = 10 * 1024 * 1024;
const supported = window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.MediaRecorder;
const mime = supported ? ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
  .find(type => MediaRecorder.isTypeSupported(type)) : null;
function updateRecordButton() {
  recordButton.disabled = !mime || acquiring || (!recording && input.disabled);
}
new MutationObserver(updateRecordButton).observe(input, {attributes: true, attributeFilter: ["disabled"]});
updateRecordButton();
if (!mime) voiceStatus.textContent = "Запись недоступна. Используйте текст; микрофону нужны HTTPS или localhost и поддержка браузера.";
function releaseMicrophone() {
  clearTimeout(timer); microphone?.getTracks().forEach(track => track.stop()); microphone = null;
}
function stopRecording(discard = false) {
  cancelled = discard;
  if (recorder?.state === "recording") recorder.stop();
  releaseMicrophone();
}
recordButton.addEventListener("click", async () => {
  if (recording) { stopRecording(); return; }
  acquiring = true; busy(true); updateRecordButton();
  window.speechSynthesis?.cancel(); voiceStatus.textContent = "Ожидаю доступ к микрофону…";
  try {
    microphone = await navigator.mediaDevices.getUserMedia({audio: true});
    recorder = new MediaRecorder(microphone, {mimeType: mime});
    chunks = []; audioSize = 0; cancelled = false;
    recorder.ondataavailable = event => {
      if (event.data.size) { chunks.push(event.data); audioSize += event.data.size; }
      if (audioSize > maxBytes) { voiceStatus.textContent = "Запись слишком большая."; stopRecording(true); }
    };
    recorder.onerror = () => { voiceStatus.textContent = "Ошибка записи. Введите текст."; stopRecording(true); };
    recorder.onstop = async () => {
      recording = false; releaseMicrophone(); discardButton.hidden = true;
      recordButton.textContent = "Записать голос"; updateRecordButton();
      try {
        if (cancelled) { voiceStatus.textContent = "Запись отменена."; return; }
        if (!audioSize || audioSize > maxBytes) throw new Error("Запись пустая или слишком большая.");
        voiceStatus.textContent = "Распознаю…";
        const blob = new Blob(chunks, {type: mime});
        const result = await request("/api/v1/speech/transcriptions", {
          method: "POST", headers: {"Content-Type": mime}, body: blob
        });
        input.value = result.text;
        voiceStatus.textContent = result.simulated
          ? "Это заранее заданный пример, а не распознавание записи. Исправьте текст и нажмите «Отправить»."
          : "Проверьте распознанный текст и нажмите «Отправить».";
      } catch (error) { voiceStatus.textContent = `${error.message} Текстовый ввод доступен.`; }
      finally { chunks = []; recorder = null; busy(false); updateRecordButton(); input.focus(); }
    };
    recorder.start(250); recording = true; acquiring = false;
    recordButton.textContent = "Остановить запись"; discardButton.hidden = false;
    voiceStatus.textContent = "Идёт запись — не более 60 секунд.";
    updateRecordButton(); timer = setTimeout(() => stopRecording(), 60000);
  } catch (error) {
    releaseMicrophone(); acquiring = false; recording = false; busy(false); updateRecordButton();
    voiceStatus.textContent = "Не удалось включить микрофон. Проверьте разрешение браузера или введите текст.";
  }
});
discardButton.addEventListener("click", () => stopRecording(true));
window.addEventListener("pagehide", () => { stopRecording(true); window.speechSynthesis?.cancel(); });
if (!window.speechSynthesis) { speakToggle.disabled = true; stopSpeech.disabled = true; }
stopSpeech.addEventListener("click", () => window.speechSynthesis?.cancel());
speakToggle.addEventListener("change", () => { if (!speakToggle.checked) window.speechSynthesis?.cancel(); });
document.addEventListener("assistant-reply", event => {
  if (!speakToggle.checked || !window.speechSynthesis || recording || acquiring) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(event.detail.slice(0, 5000));
  utterance.lang = "ru-RU";
  utterance.onerror = () => { voiceStatus.textContent = "Озвучивание недоступно. Ответ показан текстом."; };
  window.speechSynthesis.speak(utterance);
});
