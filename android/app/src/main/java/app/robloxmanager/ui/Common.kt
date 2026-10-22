package app.robloxmanager.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.material.icons.outlined.ExpandMore
import app.robloxmanager.services
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.Bulk
import app.robloxmanager.core.Person
import coil.compose.AsyncImage
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

object C {
    val bg = Color(0xFF13151A)
    val surface = Color(0xFF1A1D24)
    val surface2 = Color(0xFF222630)
    val surface3 = Color(0xFF2B303C)
    val border = Color(0xFF2A2F3A)
    val text = Color(0xFFE7EAF0)
    val muted = Color(0xFF8D96A7)
    val accent = Color(0xFF2F8CFF)
    val accentDim = Color(0xFF1D3A63)
    val success = Color(0xFF35C27A)
    val warn = Color(0xFFF0A73A)
    val danger = Color(0xFFEF5B5B)
    val dangerDim = Color(0xFF3D2227)
}

private val scheme: ColorScheme = darkColorScheme(
    primary = C.accent, onPrimary = Color.White, background = C.bg, onBackground = C.text, surface = C.surface, onSurface = C.text,
    surfaceVariant = C.surface2, onSurfaceVariant = C.muted, error = C.danger, outline = C.border, secondaryContainer = C.accentDim,
    onSecondaryContainer = C.text, surfaceContainer = C.surface, surfaceContainerHigh = C.surface2, surfaceContainerHighest = C.surface3,
)

@Composable fun AppTheme(content: @Composable () -> Unit) = MaterialTheme(colorScheme = scheme) {
    androidx.compose.material3.Surface(color = C.bg, contentColor = C.text, content = content)
}

/** What a screen's data is doing. */
sealed class Load<out T> {
    data object Idle : Load<Nothing>()
    data object Busy : Load<Nothing>()
    class Ok<T>(val value: T) : Load<T>()
    class Failed(val message: String) : Load<Nothing>()
}

fun errorText(e: Throwable): String = when (e) {
    is app.robloxmanager.core.RobloxException -> when (e.status) {
        401 -> "Signed out or the cookie is no longer valid. Sign in again."
        429 -> "Roblox is rate-limiting: ${e.message}"
        0 -> e.message ?: "Network error"
        else -> e.message ?: "Request failed (${e.status})"
    }
    else -> e.message ?: e.javaClass.simpleName
}

/** Loads something in the background; load() again to refresh. */
class Loader<T>(private val scope: CoroutineScope, private val fetch: suspend () -> T) {
    var state by mutableStateOf<Load<T>>(Load.Idle)
        private set

    fun load() {
        if (state is Load.Busy) return
        val before = state
        state = Load.Busy
        scope.launch {
            try {
                state = Load.Ok(fetch())
            } catch (e: CancellationException) {
                state = before
                throw e
            } catch (e: Exception) {
                state = Load.Failed(errorText(e))
            }
        }
    }

    val value: T? get() = (state as? Load.Ok)?.value
    fun set(v: T) { state = Load.Ok(v) }
}

@Composable
fun <T> rememberLoader(key: Any? = null, auto: Boolean = true, fetch: suspend () -> T): Loader<T> {
    val scope = rememberCoroutineScope()
    val l = remember(key) { Loader(scope, fetch) }
    LaunchedEffect(l) { if (auto && l.state is Load.Idle) l.load() }
    return l
}

@Composable
fun <T> LoadView(l: Loader<T>, content: @Composable (T) -> Unit) {
    when (val s = l.state) {
        is Load.Ok -> content(s.value)
        is Load.Failed -> Column(Modifier.fillMaxSize().padding(24.dp), Arrangement.Center, Alignment.CenterHorizontally) {
            Text(s.message, color = C.danger)
            Spacer(Modifier.height(12.dp))
            OutlinedButton(onClick = { l.load() }) { Text("Try again") }
        }
        else -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
    }
}

/** A titled block. With [collapsible] the title has an arrow: press it to hide or show what is inside (remembered between runs). */
@Composable
fun Section(title: String, collapsible: Boolean = false, content: @Composable () -> Unit) {
    val prefs = androidx.compose.ui.platform.LocalContext.current.services.prefs
    var open by remember(title) { mutableStateOf(!collapsible || !prefs.bool("fold.$title", false)) }
    val turn by androidx.compose.animation.core.animateFloatAsState(if (open) 0f else -90f, label = "arrow")
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).let { if (collapsible) it.clickable { open = !open; prefs.put("fold.$title", !open) } else it }.padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(title, Modifier.weight(1f), color = C.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            if (collapsible) androidx.compose.material3.Icon(
                androidx.compose.material.icons.Icons.Outlined.ExpandMore, if (open) "Hide $title" else "Show $title", Modifier.size(20.dp).rotate(turn), tint = C.muted,
            )
        }
        androidx.compose.animation.AnimatedVisibility(open) {
            Column { Spacer(Modifier.height(4.dp)); content() }
        }
    }
}

@Composable
fun Card(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable () -> Unit) {
    val m = modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(C.surface)
    Box(if (onClick != null) m.clickable(onClick = onClick) else m) { Box(Modifier.padding(12.dp)) { content() } }
}

@Composable
fun Avatar(url: String?, size: Int = 44) {
    Box(Modifier.size(size.dp).clip(CircleShape).background(C.surface3)) {
        if (!url.isNullOrEmpty()) AsyncImage(model = url, contentDescription = null, modifier = Modifier.size(size.dp))
    }
}

@Composable
fun PersonRow(p: Person, avatar: String?, selected: Boolean? = null, onToggle: (() -> Unit)? = null, onClick: (() -> Unit)? = null, trailing: @Composable () -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it }.padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (selected != null) Checkbox(checked = selected, onCheckedChange = { onToggle?.invoke() })
        Avatar(avatar)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(p.title + if (p.verified) "  ✔" else "", maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
            val sub = listOf(p.handle, p.extra).filter { it.isNotEmpty() }.joinToString("  ·  ")
            if (sub.isNotEmpty()) Text(sub, color = C.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        trailing()
    }
}

@Composable
fun Confirm(title: String, text: String, ok: String = "Yes", danger: Boolean = false, onYes: () -> Unit, onNo: () -> Unit) {
    AlertDialog(
        onDismissRequest = onNo, title = { Text(title) }, text = { Text(text, color = C.muted) },
        confirmButton = { TextButton(onClick = { onYes() }) { Text(ok, color = if (danger) C.danger else C.accent) } },
        dismissButton = { TextButton(onClick = onNo) { Text("Cancel") } },
    )
}

@Composable
fun PrimaryButton(text: String, enabled: Boolean = true, onClick: () -> Unit) =
    Button(onClick = onClick, enabled = enabled, shape = RoundedCornerShape(10.dp)) { Text(text) }

@Composable
fun DangerButton(text: String, enabled: Boolean = true, onClick: () -> Unit) =
    Button(onClick = onClick, enabled = enabled, shape = RoundedCornerShape(10.dp), colors = ButtonDefaults.buttonColors(containerColor = C.dangerDim, contentColor = C.danger)) { Text(text) }

@Composable
fun QuietButton(text: String, enabled: Boolean = true, onClick: () -> Unit) =
    OutlinedButton(onClick = onClick, enabled = enabled, shape = RoundedCornerShape(10.dp)) { Text(text) }

/** Progress of a batch with a Stop button; shows what failed afterwards. */
@Composable
fun BulkBar(bulk: Bulk) {
    val s by bulk.state.collectAsState()
    if (!s.active) return
    Column(Modifier.fillMaxWidth().background(C.surface2).padding(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            val head = when {
                s.running -> "${s.label}: ${s.done} of ${s.total}"
                s.stopped -> "${s.label}: stopped after ${s.done} of ${s.total}"
                else -> "${s.label}: done (${s.total - s.failed.count { !it.startsWith("Signed out") }} of ${s.total})"
            }
            Text(head, Modifier.weight(1f), fontWeight = FontWeight.Medium)
            if (s.running) TextButton(onClick = { bulk.stop() }) { Text("Stop", color = C.danger) } else TextButton(onClick = { bulk.dismiss() }) { Text("Close") }
        }
        if (s.running) LinearProgressIndicator(progress = { if (s.total == 0) 0f else s.done.toFloat() / s.total }, modifier = Modifier.fillMaxWidth())
        if (s.failed.isNotEmpty()) {
            Spacer(Modifier.height(6.dp))
            Text("${s.failed.size} problem(s):", color = C.warn, fontSize = 12.sp)
            s.failed.take(4).forEach { Text(it, color = C.muted, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis) }
            if (s.failed.size > 4) Text("… and ${s.failed.size - 4} more (see Request log)", color = C.muted, fontSize = 12.sp)
        }
    }
}
