// NoteBox: the engine behind every app. The app id is the second part of the path: /a/<id>/<page>.
(function () {
  const segs = location.pathname.split("/").filter(Boolean);
  const id = segs[1];
  const cfg = window.APPS[id];
  const root = document.getElementById("root");
  if (!cfg) {
    root.innerHTML = '<main><div class="card"><h1>NoteBox</h1><p>This app does not exist.</p></div></main>';
    return;
  }

  const LS = {
    get(k, d) { try { const v = JSON.parse(localStorage.getItem(`lab.${id}.${k}`)); return v === null || v === undefined ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(`lab.${id}.${k}`, JSON.stringify(v)); } catch (e) { /* storage blocked */ } },
    del(k) { try { localStorage.removeItem(`lab.${id}.${k}`); } catch (e) { /* storage blocked */ } },
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const base = `/a/${id}`;
  const way = cfg.way;
  const variant = cfg.variant;
  let handlers = [];

  // ---- small helpers -------------------------------------------------------------------------
  const field = (label, name, type, extra) =>
    `<label for="${name}">${label}</label><input id="${name}" name="${name}" type="${type || "text"}" ${extra || ""}>`;
  const val = (name) => (document.getElementById(name) || {}).value || "";
  const say = (msg, ok) => {
    const e = document.getElementById("msg");
    if (e) { e.className = ok ? "ok" : "err"; e.textContent = msg; }
  };
  const go = (page, query) => {
    history.pushState({}, "", `${base}${page ? "/" + page : ""}${query || ""}`);
    render();
  };
  const shell = (inner, who) => {
    root.innerHTML = `<header class="bar"><strong>NoteBox</strong><span>${who || ""}</span></header><main>${inner}</main>`;
  };
  const card = (inner) => `<div class="card">${inner}</div>`;
  const modal = (title, inner) =>
    `<div class="scrim"><div class="card" role="dialog" aria-modal="true" aria-labelledby="mt"><h1 id="mt">${title}</h1>${inner}</div></div>`;
  const form = (inner, onSubmit) => {
    handlers.push(onSubmit);
    return `<form data-h="${handlers.length - 1}" novalidate>${inner}</form>`;
  };
  const wire = () => {
    document.querySelectorAll("form[data-h]").forEach((f) => {
      const fn = handlers[Number(f.dataset.h)];
      f.addEventListener("submit", (e) => { e.preventDefault(); fn(); });
    });
    document.querySelectorAll("[data-go]").forEach((b) =>
      b.addEventListener("click", (e) => { e.preventDefault(); go(b.dataset.go); }));
    document.querySelectorAll("[data-act]").forEach((b) =>
      b.addEventListener("click", (e) => { e.preventDefault(); ACTIONS[b.dataset.act](b); }));
  };
  const accounts = () => LS.get("accounts", []);
  const findAccount = (email) => accounts().find((a) => a.email.toLowerCase() === String(email).trim().toLowerCase());
  const addAccount = (a) => LS.set("accounts", accounts().concat(a));
  const markVerified = (email) => LS.set("accounts", accounts().map((a) => (a.email === email ? Object.assign({}, a, { verified: true }) : a)));
  const signInAs = (who) => { LS.set("session", who); go("notes"); };

  async function api(path, body) {
    try {
      const r = await fetch(`/api/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await r.json().catch(() => ({}));
      return r.ok ? data : { error: data.error || "Something went wrong. Try again." };
    } catch (e) { return { error: "Could not reach the server. Try again." }; }
  }

  // ---- the notes app, the same behind every login --------------------------------------------
  function notesView() {
    const who = LS.get("session", null);
    if (!who) return go("");
    const key = `notes.${who}`;
    const notes = LS.get(key, []);
    const guest = who === "guest";
    shell(card(`
      <h1>Your notes</h1>
      <p class="hint">${guest ? "You are using NoteBox as a guest." : `Signed in as ${esc(who)}`}</p>
      ${form(field("Note title", "title", "text", 'maxlength="80"') + '<button type="submit">Add note</button><p id="msg" role="alert" class="err"></p>', () => {
        const t = val("title").trim();
        if (!t) return say("Write a title first.");
        LS.set(key, LS.get(key, []).concat({ t, at: Date.now() }));
        notesView();
      })}
      <p aria-live="polite">${notes.length === 0 ? "No notes yet." : `${notes.length} note${notes.length === 1 ? "" : "s"}`}</p>
      <ul class="notes">${notes.map((n, i) => `<li><span>${esc(n.t)}</span><button class="link" data-act="del" data-i="${i}" aria-label="Delete ${esc(n.t)}">Delete</button></li>`).join("")}</ul>
      <button class="ghost" data-act="out">${guest ? "Leave guest mode" : "Sign out"}</button>`),
    guest ? "Guest" : esc(who));
    wire();
  }
  const ACTIONS = {
    out() { LS.del("session"); LS.del("modal"); go(""); },
    del(b) { const k = `notes.${LS.get("session")}`; const n = LS.get(k, []); n.splice(Number(b.dataset.i), 1); LS.set(k, n); notesView(); },
    guest() { signInAs("guest"); },
    signin() { LS.set("modal", "signin"); render(); },
    closeModal() { LS.del("modal"); render(); },
    tab(b) { LS.set("tab", b.dataset.t); render(); },
    resend() { sendAgain(); },
  };

  // ---- pieces shared by the ways in ----------------------------------------------------------
  const tabs = (items, current) =>
    `<div class="tabs" role="tablist">${items.map((it) =>
      `<button role="tab" type="button" aria-selected="${it[0] === current}" data-act="tab" data-t="${it[0]}">${it[1]}</button>`).join("")}</div>`;

  function pwSignIn(title, extra) {
    return form(`<h1>${title || "Sign in"}</h1>${field("Email", "email", "email", 'autocomplete="email"')}${field("Password", "password", "password", 'autocomplete="current-password"')}${extra || ""}
      <button type="submit">Sign in</button><p id="msg" role="alert" class="err"></p>`, () => {
      const a = findAccount(val("email"));
      if (!a || a.password !== val("password")) return say("Wrong email or password.");
      if (a.verified === false) return say("Please confirm your email first. We sent you a link.");
      signInAs(a.email);
    });
  }
  // a sign-in form for the guest apps: there are no accounts, so it always says so
  function noAccountSignIn(title) {
    return form(`<h1>${title || "Sign in"}</h1>${field("Email", "email", "email")}${field("Password", "password", "password")}
      <button type="submit">Sign in</button><p id="msg" role="alert" class="err"></p>`, () => say("No account found for this email."));
  }
  const welcome = '<h1>Welcome to NoteBox</h1><p class="hint">Keep your notes in one place.</p><button type="button" data-go="signup">Create account</button> <button type="button" class="ghost" data-go="signin">Sign in</button>';

  // ---- guest ---------------------------------------------------------------------------------
  function guestView(page) {
    if (variant === "header") {
      root.innerHTML = `<header class="bar"><strong>NoteBox</strong><button type="button" class="ghost" style="margin:0" data-act="guest">Continue as guest</button></header>
        <main>${card(`<p class="hint">Sign in to keep your notes.</p>${noAccountSignIn("Welcome to NoteBox")}`)}</main>`;
    } else if (variant === "modal") {
      const showForm = LS.get("modal", "") === "signin";
      shell(card('<h1>NoteBox</h1><p class="hint">A small place for your notes.</p>') +
        (showForm ? modal("Sign in", noAccountSignIn("Your account") + '<button type="button" class="ghost" data-act="closeModal">Back</button>')
          : modal("Welcome to NoteBox", '<button type="button" data-act="signin">Sign in</button> <button type="button" class="ghost" data-act="guest">Try the demo</button>')));
    } else if (variant === "skip") {
      shell(card(`${noAccountSignIn("Sign in to NoteBox")}<button type="button" class="link" data-act="guest">Skip for now</button>`));
    } else if (page === "theme") {
      shell(card(`<h1>Pick a look</h1>${form(`<div class="row"><input type="radio" id="light" name="theme" checked><label for="light">Light</label></div>
        <div class="row"><input type="radio" id="dark" name="theme"><label for="dark">Dark</label></div><button type="submit">Start using NoteBox</button>`, () => signInAs("guest"))}`));
    } else {
      shell(card(`<h1>Welcome to NoteBox</h1><p class="hint">Step 1 of 2</p>${noAccountSignIn("Sign in")}
        <button type="button" class="ghost" data-go="theme">Skip</button>`));
    }
    wire();
  }

  // ---- email and password --------------------------------------------------------------------
  function pwView(page) {
    if (variant === "tabs") {
      const t = LS.get("tab", "up");
      shell(card(`<h1>NoteBox</h1>${tabs([["up", "Create account"], ["in", "Sign in"]], t)}${t === "up" ?
        form(`${field("Full name", "name", "text", 'autocomplete="name"')}${field("Email", "email", "email")}${field("Password", "password", "password", 'autocomplete="new-password"')}
          <button type="submit">Create account</button><p id="msg" role="alert" class="err"></p>`, () => {
          if (!val("name").trim()) return say("Enter your name.");
          if (!/^\S+@\S+\.\S+$/.test(val("email"))) return say("Enter a valid email address.");
          if (val("password").length < 8) return say("Password must be at least 8 characters.");
          if (findAccount(val("email"))) return say("An account with this email already exists. Sign in instead.");
          addAccount({ email: val("email").trim(), password: val("password"), name: val("name"), verified: true });
          signInAs(val("email").trim());
        }) : pwSignIn()}`));
    } else if (page === "signup") {
      const rules = variant === "rules";
      const terms = variant === "terms";
      shell(card(form(`<h1>Create your account</h1>${rules ? field("Username", "username", "text", 'autocomplete="username"') : ""}${field("Email", "email", "email")}
        ${field("Password", "password", "password", 'autocomplete="new-password"')}${rules ? '<p class="hint">At least 12 characters, with a number and a symbol.</p>' + field("Confirm password", "confirm", "password") : ""}
        ${terms ? '<div class="row"><input type="checkbox" id="terms"><label for="terms">I agree to the terms</label></div>' : ""}
        <button type="submit">Create account</button><p id="msg" role="alert" class="err"></p>`, () => {
        const pw = val("password");
        if (rules && !val("username").trim()) return say("Choose a username.");
        if (!/^\S+@\S+\.\S+$/.test(val("email"))) return say("Enter a valid email address.");
        if (rules) {
          if (pw.length < 12) return say("Password must be at least 12 characters.");
          if (!/\d/.test(pw) || !/[^A-Za-z0-9]/.test(pw)) return say("Password needs a number and a symbol.");
          if (pw !== val("confirm")) return say("The passwords do not match.");
        } else if (pw.length < 8) return say("Password must be at least 8 characters.");
        if (terms && !document.getElementById("terms").checked) return say("You must agree to the terms.");
        if (findAccount(val("email"))) return say("An account with this email already exists. Sign in instead.");
        addAccount({ email: val("email").trim(), password: pw, verified: true });
        if (terms) { LS.set("notice", "Account created. Please sign in."); return go("signin"); }
        signInAs(val("email").trim());
      })) + '<p class="hint">Already have an account? <button type="button" class="link" data-go="signin">Sign in</button></p>');
    } else if (page === "signin") {
      const notice = LS.get("notice", ""); LS.del("notice");
      shell(card((notice ? `<p class="ok">${notice}</p>` : "") +
        pwSignIn("Sign in", variant === "terms" ? '<div class="row"><input type="checkbox" id="remember"><label for="remember">Remember me</label></div>' : "")));
    } else {
      shell(card(welcome));
    }
    wire();
  }

  // ---- sending and checking codes (email code, email link, text message) ----------------------
  async function startChallenge(kind, target, extra) {
    const r = await api("challenge", { app: id, kind, target });
    if (r.error) { say(r.error); return false; }
    LS.set("pending", Object.assign({ ch: r.ch, target }, extra || {}));
    return true;
  }
  function sendAgain() {
    const p = LS.get("pending", null);
    if (!p) return;
    api("challenge", { app: id, kind: way === "link" ? "link" : way === "phone" ? "sms" : "code", target: p.target }).then((r) => {
      if (r.error) return say(r.error);
      LS.set("pending", Object.assign({}, p, { ch: r.ch }));
      say("A new one was sent.", true);
    });
  }
  async function finishCode(code) {
    const p = LS.get("pending", null);
    if (!p) return say("Start again, please.");
    const r = await api("verify", { ch: p.ch, code });
    if (r.error) return say(r.error);
    if (!findAccount(p.target)) addAccount({ email: p.target, password: p.password, verified: true });
    LS.del("pending"); LS.del("modal");
    signInAs(p.target);
  }
  const codeBoxes = () => `<label for="d1">Verification code</label><div class="digits">${[1, 2, 3, 4, 5, 6].map((n) =>
    `<input id="d${n}" inputmode="numeric" maxlength="1" aria-label="Digit ${n}" autocomplete="one-time-code">`).join("")}</div>`;
  function wireBoxes() {
    const ins = [1, 2, 3, 4, 5, 6].map((n) => document.getElementById("d" + n));
    ins.forEach((el, i) => {
      el.addEventListener("input", () => { el.value = el.value.replace(/\D/g, "").slice(-1); if (el.value && ins[i + 1]) ins[i + 1].focus(); });
      el.addEventListener("keydown", (e) => { if (e.key === "Backspace" && !el.value && ins[i - 1]) ins[i - 1].focus(); });
      el.addEventListener("paste", (e) => {
        const d = (e.clipboardData.getData("text") || "").replace(/\D/g, "").slice(0, 6);
        if (d.length > 1) { e.preventDefault(); d.split("").forEach((c, k) => { if (ins[k]) ins[k].value = c; }); }
      });
    });
  }
  function codeForm() {
    const p = LS.get("pending", {});
    const boxes = variant === "boxes";
    return form(`<p class="hint">We ${way === "phone" ? "texted" : "emailed"} a 6-digit code to ${esc(p.target || "you")}. It expires in 10 minutes.</p>
      ${boxes ? codeBoxes() : field("Verification code", "code", "text", 'inputmode="numeric" autocomplete="one-time-code" maxlength="6"')}
      <button type="submit">Verify</button> <button type="button" class="ghost" data-act="resend">Resend code</button><p id="msg" role="alert" class="err"></p>`,
    () => finishCode(boxes ? [1, 2, 3, 4, 5, 6].map((n) => val("d" + n)).join("") : val("code").trim()));
  }

  // ---- email code ----------------------------------------------------------------------------
  function codeView(page) {
    const passwordless = variant === "passwordless";
    const start = (title, withPw) => form(`<h1>${title}</h1>${field("Email", "email", "email", 'autocomplete="email"')}${withPw ? field("Password", "password", "password", 'autocomplete="new-password"') : ""}
      <button type="submit">${withPw ? "Create account" : "Continue with email"}</button><p id="msg" role="alert" class="err"></p>`, async () => {
      const email = val("email").trim();
      if (withPw && val("password").length < 8) return say("Password must be at least 8 characters.");
      if (withPw && findAccount(email)) return say("An account with this email already exists. Sign in instead.");
      say("Sending your code...", true);
      if (await startChallenge("code", email, { password: val("password") })) {
        if (variant === "modal") { LS.set("modal", "code"); render(); } else go("code");
      }
    });
    if (page === "signin" && !passwordless) {
      shell(card(pwSignIn()));
    } else if (page === "code") {
      shell(card(`<h1>Check your email</h1>${codeForm()}`));
    } else if (passwordless) {
      shell(card(start("Sign in or sign up with your email", false)));
    } else if (page === "signup") {
      const showCode = variant === "modal" && LS.get("modal", "") === "code";
      shell(card(start("Create your account", true)) + (showCode ? modal("Enter your code", codeForm()) : ""));
    } else {
      shell(card(welcome));
    }
    wire();
    if (variant === "boxes" && page === "code") wireBoxes();
  }

  // ---- email link ----------------------------------------------------------------------------
  function linkView(page) {
    const magic = variant === "magic";
    const start = (title) => form(`<h1>${title}</h1>${variant === "continue" ? field("Full name", "name") : ""}${field("Email", "email", "email")}${magic ? "" : field("Password", "password", "password", 'autocomplete="new-password"')}
      <button type="submit">${magic ? "Email me a sign-in link" : "Create account"}</button><p id="msg" role="alert" class="err"></p>`, async () => {
      const email = val("email").trim();
      if (!magic && val("password").length < 8) return say("Password must be at least 8 characters.");
      if (!magic && findAccount(email)) return say("An account with this email already exists. Sign in instead.");
      say("Sending your email...", true);
      if (!(await startChallenge("link", email, { password: val("password") }))) return;
      if (!magic) addAccount({ email, password: val("password"), verified: false });
      go("sent");
    });
    if (page === "sent") {
      const p = LS.get("pending", {});
      shell(card(`<h1>Check your inbox</h1><p>We sent a ${magic ? "sign-in" : "confirmation"} link to <strong>${esc(p.target || "your email")}</strong>. It is valid for 15 minutes.</p>
        <button type="button" class="ghost" data-act="resend">Resend email</button><p id="msg" role="alert" class="err"></p>`));
    } else if (page === "verify") {
      shell(card('<h1>Confirming your email</h1><p id="msg" aria-live="polite">One moment...</p>'));
      verifyLink();
    } else if (page === "signin" && !magic) {
      const notice = LS.get("notice", ""); LS.del("notice");
      shell(card((notice ? `<p class="ok">${notice}</p>` : "") + pwSignIn()));
    } else if (page === "signup" || magic) {
      shell(card(start(magic ? "Sign in with your email" : "Create your account")));
    } else {
      shell(card(welcome));
    }
    wire();
  }
  async function verifyLink() {
    const q = new URLSearchParams(location.search);
    const r = await api("verify", { ch: q.get("ch"), code: q.get("c") });
    const out = document.getElementById("msg");
    if (r.error) { out.className = "err"; out.textContent = "This link is not valid or has expired."; return; }
    const email = r.target;
    if (findAccount(email)) markVerified(email); else addAccount({ email, verified: true });
    if (variant === "activate") { LS.set("notice", "Email confirmed. Please sign in."); setTimeout(() => go("signin"), 700); return; }
    if (variant === "continue") {
      out.className = "ok";
      out.innerHTML = 'Your email is confirmed. <button type="button" data-act="cont">Continue to your notes</button>';
      ACTIONS.cont = () => signInAs(email);
      wire();
      return;
    }
    out.className = "ok"; out.textContent = "Email confirmed. Taking you to your notes...";
    setTimeout(() => signInAs(email), 700);
  }

  // ---- Google, GitHub or Apple only ----------------------------------------------------------
  const PROVIDERS = {
    google: ["Continue with Google", "https://accounts.google.com/signin"],
    github: ["Continue with GitHub", "https://github.com/login"],
    apple: ["Continue with Apple", "https://appleid.apple.com/sign-in"],
  };
  function oauthView() {
    shell(card(`<h1>Sign in to NoteBox</h1><p class="hint">Use your ${cfg.providers.map((p) => p[0].toUpperCase() + p.slice(1)).join(" or ")} account.</p>
      ${cfg.providers.map((p) => `<a class="btn ghost" style="display:block;text-align:center" href="${PROVIDERS[p][1]}">${PROVIDERS[p][0]}</a>`).join("")}`));
  }

  // ---- phone ---------------------------------------------------------------------------------
  function phoneView(page) {
    const tab = LS.get("tab", "phone");
    const start = form(`<h1>Sign in with your phone</h1>${variant === "modal" ? field("Your name", "name") : ""}
      ${variant === "country" ? '<label for="phone">Phone number</label><div class="split"><select id="cc" aria-label="Country"><option value="91">India +91</option><option value="1">United States +1</option><option value="44">United Kingdom +44</option></select><input id="phone" type="tel" aria-label="Phone number" autocomplete="tel-national"></div>'
        : field("Phone number", "phone", "tel", 'autocomplete="tel"')}
      <button type="submit">Send code</button><p id="msg" role="alert" class="err"></p>`, async () => {
      const digits = val("phone").replace(/\D/g, "");
      if (digits.length < 10) return say("Enter a valid phone number.");
      const national = digits.slice(-10);
      const cc = variant === "country" ? val("cc") : (digits.length > 10 ? digits.slice(0, digits.length - 10) : "91");
      say("Sending your code...", true);
      if (await startChallenge("sms", `+${cc}${national}`)) {
        if (variant === "modal") { LS.set("modal", "code"); render(); } else go("code");
      }
    });
    if (page === "code") shell(card(`<h1>Check your phone</h1>${codeForm()}`));
    else if (variant === "tabs") shell(card(`<h1>NoteBox</h1>${tabs([["phone", "Phone"], ["email", "Email"]], tab)}${tab === "phone" ? start : "<p>Email sign-in is coming soon. Use your phone for now.</p>"}`));
    else shell(card(start) + (variant === "modal" && LS.get("modal", "") === "code" ? modal("Enter your code", codeForm()) : ""));
    wire();
  }

  // ---- routing -------------------------------------------------------------------------------
  function render() {
    handlers = [];
    const page = location.pathname.split("/").filter(Boolean)[2] || "";
    if (page === "notes") return notesView();
    if (way === "guest") return guestView(page);
    if (way === "pw") return pwView(page);
    if (way === "code") return codeView(page);
    if (way === "link") return linkView(page);
    if (way === "oauth") return oauthView();
    if (way === "phone") return phoneView(page);
  }
  addEventListener("popstate", render);
  render();
})();
