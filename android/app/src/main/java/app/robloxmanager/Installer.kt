package app.robloxmanager

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import app.robloxmanager.core.AppUpdate
import app.robloxmanager.core.UpdateError
import app.robloxmanager.core.UpdateInfo
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Update state shared by the start-up check and the Settings screen. */
data class UpdateState(val message: String = "", val available: UpdateInfo? = null, val ready: File? = null, val busy: Boolean = false, val progress: Float = 0f)

object Updates {
    val state = MutableStateFlow(UpdateState())
    const val DEFAULT_URL = ""      // set in Settings (or baked in by tools/release.sh): the raw address of the repository's dist/ folder

    fun url(sv: Services) = sv.prefs.str("updateUrl", DEFAULT_URL)

    /** Looks for a newer build and, if there is one, downloads and verifies it so it is ready to install. Never throws. */
    fun check(sv: Services, ctx: Context, download: Boolean = true, quiet: Boolean = false) {
        val url = url(sv)
        if (url.isBlank()) { if (!quiet) state.value = UpdateState("Set the update address first."); return }
        if (state.value.busy) return
        state.value = state.value.copy(busy = true, message = if (quiet) state.value.message else "Checking…", progress = 0f)
        sv.scope.launch {
            try {
                val u = AppUpdate(url)
                val info = withContext(Dispatchers.IO) { u.check(BuildConfig.VERSION_CODE) }
                if (info == null) { state.value = UpdateState("You have the newest version (${BuildConfig.VERSION_NAME})."); return@launch }
                state.value = UpdateState("Version ${info.versionName} is available.", info, busy = download)
                if (download) {
                    val f = withContext(Dispatchers.IO) { u.download(info, File(ctx.cacheDir, "updates")) { d, t -> if (t > 0) state.value = state.value.copy(progress = d.toFloat() / t) } }
                    state.value = UpdateState("Version ${info.versionName} is ready to install.", info, f)
                }
            } catch (e: UpdateError) {
                state.value = UpdateState(if (quiet) "" else (e.message ?: "Update failed"))
            } catch (e: Exception) {
                state.value = UpdateState(if (quiet) "" else "Update failed: ${e.javaClass.simpleName}")
            }
        }
    }

    /** Hands the verified APK to Android's installer. The system asks the user to confirm (and, once, to allow installs from this app). */
    fun install(ctx: Context, apk: File): String {
        if (!ctx.packageManager.canRequestPackageInstalls()) {
            ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return "Allow installs from this app, then press Install again."
        }
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", apk)
        ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
        return "Installer opened."
    }
}
