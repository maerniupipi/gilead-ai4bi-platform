(() => {
  "use strict";
  const form = document.getElementById("login-form");
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = document.getElementById("login-submit");
    const errorBox = document.getElementById("login-error");
    button.disabled = true;
    button.textContent = "正在登录…";
    errorBox.hidden = true;
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-Local-Request": "1"},
        body: JSON.stringify({username: document.getElementById("username").value.trim(),
          password: document.getElementById("password").value})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "登录失败，请检查输入");
      document.getElementById("password").value = "";
      window.location.replace("/");
    } catch (error) {
      errorBox.textContent = error.message || "连接失败，请稍后再试";
      errorBox.hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = "登录 ↗";
    }
  });
})();
