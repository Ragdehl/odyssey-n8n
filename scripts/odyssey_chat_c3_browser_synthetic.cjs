"use strict";
// Click the REAL Odyssey browser UI, not DOM injection or direct API calls.
// Synthetic n8n bridge; provider is fixed by default or real Luna with a bounded gate.
const path = require("node:path");
const puppeteer = require(process.env.ODYSSEY_PUPPETEER_MODULE ||
  path.join(process.env.HOME || "/home/ragdehl",
    ".npm/_npx/4b4c857f6efdfb61/node_modules/puppeteer"));
const chrome = process.env.ODYSSEY_CHROMIUM_BINARY ||
  path.join(process.env.HOME || "/home/ragdehl",
    ".cache/puppeteer/chrome/linux_arm-154.0.8037.57/chrome-linux-arm64/chrome");

(async () => {
  let browser;
  try {
    const address = process.argv[2];
    if (!/^http:\/\/127\.0\.0\.1:\d+\/$/.test(address || "")) {
      throw new Error("Browser must use ephemeral localhost app");
    }
    browser = await puppeteer.launch({
      executablePath: chrome, headless: true,
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
        "--disable-background-networking"],
    });
    const page = await browser.newPage();
    await page.setViewport({width: 390, height: 844, deviceScaleFactor: 1});
    const errors = [];
    page.on("pageerror", e => errors.push(String(e.message).slice(0, 120)));
    await page.goto(address, {waitUntil: "domcontentloaded", timeout: 20000});
    await page.waitForSelector("#request-input", {timeout: 12000});
    const realProvider = process.env.ODYSSEY_CHAT_BROWSER_REAL === "1";
    async function submit(source, expected, count) {
      await page.type("#request-input", source, {delay: 1});
      await page.click("#send-button");
      await page.waitForFunction(
        (n, text) => document.querySelectorAll(".message-odyssey:not(.message-loading)").length === n &&
          (!text || [...document.querySelectorAll(".message-odyssey:not(.message-loading) .message-text")]
            .some(node => node.textContent.toLowerCase().includes(text.toLowerCase()))),
        {timeout: realProvider ? 60000 : 8000}, count, expected
      );
      return await page.evaluate(() => ({
        user: document.querySelectorAll(".message-user").length,
        assistant: document.querySelectorAll(".message-odyssey").length,
        texts: [...document.querySelectorAll(".message-odyssey .message-text")]
          .map(item => item.textContent),
        noteSets: document.querySelectorAll(".note-set-button").length,
      }));
    }
    const afterSocial = await submit("Hola", realProvider ? null : "¡Hola desde Odyssey!", 1);
    const afterHelp = await submit("¿Cómo creo subtareas?", realProvider ? "subtarea" : "Puedes añadir subtareas", 2);
    await page.reload({waitUntil: "domcontentloaded", timeout: 20000});
    await page.waitForFunction(
      () => document.querySelectorAll(".message-odyssey").length === 2,
      {timeout: 12000}
    );
    const reloaded = await page.evaluate(() => ({
      user: document.querySelectorAll(".message-user").length,
      assistant: document.querySelectorAll(".message-odyssey").length,
      texts: [...document.querySelectorAll(".message-odyssey .message-text")]
        .map(item => item.textContent),
      noteSets: document.querySelectorAll(".note-set-button").length,
    }));
    const pass = afterSocial.user === 1 && afterSocial.assistant === 1 &&
      afterHelp.user === 2 && afterHelp.assistant === 2 &&
      reloaded.user === 2 && reloaded.assistant === 2 &&
      (realProvider
        ? afterSocial.texts[0].trim().length > 0 &&
          afterHelp.texts[1].toLowerCase().includes("subtarea") &&
          JSON.stringify(afterHelp.texts) === JSON.stringify(reloaded.texts)
        : reloaded.texts.includes("¡Hola desde Odyssey!") &&
          reloaded.texts.includes("Puedes añadir subtareas desde una tarea.")) &&
      reloaded.noteSets === 0 && errors.length === 0;
    console.log(JSON.stringify({pass, afterSocial, afterHelp, reloaded, jsErrors: errors}));
    if (!pass) process.exitCode = 2;
  } catch (error) {
    console.log(JSON.stringify({pass: false, error: String(error.message).slice(0, 280)}));
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
  }
})();
