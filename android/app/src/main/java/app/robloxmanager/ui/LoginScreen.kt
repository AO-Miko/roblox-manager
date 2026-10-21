package app.robloxmanager.ui

import android.annotation.SuppressLint
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.foundation.text.KeyboardOptions
import app.robloxmanager.Services
import app.robloxmanager.core.Done
import app.robloxmanager.core.LoginError
import app.robloxmanager.core.NeedBrowser
import app.robloxmanager.core.PasswordLogin
import app.robloxmanager.core.TwoStep
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(sv: Services, canCancel: Boolean, onCancel: () -> Unit) {
    var tab by remember { mutableStateOf(0) }
    val titles = listOf("Password", "Browser", "Cookie")
    Column(Modifier.fillMaxSize()) {
        Text("Sign in to Roblox", fontSize = 22.sp, modifier = Modifier.padding(16.dp, 24.dp, 16.dp, 4.dp))
        Text("Your cookie is stored encrypted on this phone only and sent to roblox.com only.", color = C.muted, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp))
        Spacer(Modifier.height(12.dp))
        TabRow(selectedTabIndex = tab, containerColor = C.bg) {
            titles.forEachIndexed { i, t -> Tab(selected = tab == i, onClick = { tab = i }, text = { Text(t) }) }
        }
        when (tab) {
            0 -> PasswordTab(sv) { tab = 1 }
            1 -> BrowserTab(sv)
            else -> CookieTab(sv)
        }
        if (canCancel) QuietButtonRow("Cancel", onCancel)
    }
}

@Composable
private fun QuietButtonRow(text: String, onClick: () -> Unit) = Row(Modifier.padding(16.dp)) { QuietButton(text, onClick = onClick) }

@Composable
private fun PasswordTab(sv: Services, toBrowser: () -> Unit) {
    val scope = rememberCoroutineScope()
    val login = remember { PasswordLogin(log = sv.log) }
    var user by remember { mutableStateOf("") }
    var pass by remember { mutableStateOf("") }
    var step by remember { mutableStateOf<TwoStep?>(null) }
    var method by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var rememberDevice by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf("") }
    var needBrowser by remember { mutableStateOf(false) }

    fun finish(d: Done) {
        scope.launch {
            try { sv.signIn(d.cookie) } catch (e: Exception) { msg = errorText(e) }
            busy = false
            pass = ""
        }
    }

    fun handle(block: suspend () -> Unit) {
        busy = true; msg = ""
        scope.launch {
            try {
                block()
            } catch (e: LoginError) {
                msg = e.message ?: "Sign-in failed"
                busy = false
            } catch (e: NeedBrowser) {
                msg = e.message ?: ""
                needBrowser = true
                step = null
                busy = false
            } catch (e: Exception) {
                msg = errorText(e)
                busy = false
            }
        }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        val s = step
        if (s == null) {
            OutlinedTextField(user, { user = it }, label = { Text("Username or email") }, singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !busy)
            OutlinedTextField(pass, { pass = it }, label = { Text("Password") }, singleLine = true, visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth(), enabled = !busy)
            PrimaryButton(if (busy) "Signing in…" else "Sign in", enabled = !busy && user.isNotBlank() && pass.isNotEmpty()) {
                handle {
                    when (val r = login.start(user, pass)) {
                        is Done -> finish(r)
                        is TwoStep -> { step = r; method = r.primary; code = ""; busy = false }
                    }
                }
            }
        } else {
            Text("2-step verification", fontSize = 16.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                s.methods.forEach { m -> FilterChip(selected = method == m, onClick = { method = m; code = "" }, label = { Text(PasswordLogin.METHOD_TEXT[m] ?: m) }) }
            }
            if (method in PasswordLogin.SENDS_A_CODE) QuietButton("Send me a code", enabled = !busy) { handle { login.sendCode(method); msg = "Code sent."; busy = false } }
            OutlinedTextField(code, { code = it }, label = { Text("Code") }, singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth(), enabled = !busy)
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Checkbox(rememberDevice, { rememberDevice = it })
                Text("Remember this device")
            }
            PrimaryButton(if (busy) "Checking…" else "Verify", enabled = !busy && code.isNotBlank()) { handle { finish(login.verify(method, code, rememberDevice)) } }
            QuietButton("Back", enabled = !busy) { login.forget(); step = null; msg = "" }
        }
        if (msg.isNotEmpty()) Text(msg, color = if (msg == "Code sent.") C.success else C.danger)
        if (needBrowser) QuietButton("Use the browser sign-in instead", onClick = toBrowser)
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun BrowserTab(sv: Services) {
    val scope = rememberCoroutineScope()
    var msg by remember { mutableStateOf("Sign in on the Roblox page below. It handles every kind of check (CAPTCHA, passkey ...).") }
    val ctx = LocalContext.current
    val cm = remember { CookieManager.getInstance() }
    var web by remember { mutableStateOf<WebView?>(null) }
    var done by remember { mutableStateOf(false) }

    LaunchedEffect(web) {
        while (!done && web != null) {
            delay(1000)
            val c = cm.getCookie("https://www.roblox.com")?.split(";")?.map { it.trim() }?.firstOrNull { it.startsWith(".ROBLOSECURITY=") }
            if (c != null) {
                done = true
                msg = "Signed in, finishing…"
                try {
                    sv.signIn(c.substringAfter("="))
                    cm.removeAllCookies(null)
                } catch (e: Exception) {
                    msg = errorText(e); done = false
                    cm.removeAllCookies(null)
                    web?.loadUrl("https://www.roblox.com/login")
                }
            }
        }
    }
    DisposableEffect(Unit) { onDispose { web?.destroy() } }

    Column(Modifier.fillMaxSize()) {
        Text(msg, color = C.muted, fontSize = 12.sp, modifier = Modifier.padding(12.dp))
        AndroidView(modifier = Modifier.fillMaxWidth().weight(1f), factory = {
            cm.removeAllCookies(null)
            WebView(ctx).apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                webViewClient = WebViewClient()
                loadUrl("https://www.roblox.com/login")
                web = this
            }
        })
    }
}

@Composable
private fun CookieTab(sv: Services) {
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Paste the .ROBLOSECURITY cookie of the account. Treat it like a password: anyone who has it is signed in as you.", color = C.muted, fontSize = 13.sp)
        OutlinedTextField(text, { text = it }, label = { Text(".ROBLOSECURITY") }, modifier = Modifier.fillMaxWidth(), minLines = 3, enabled = !busy)
        PrimaryButton(if (busy) "Checking…" else "Sign in", enabled = !busy && text.isNotBlank()) {
            busy = true; msg = ""
            scope.launch {
                try { sv.signIn(text); text = "" } catch (e: Exception) { msg = errorText(e) }
                busy = false
            }
        }
        if (msg.isNotEmpty()) Text(msg, color = C.danger)
    }
}
