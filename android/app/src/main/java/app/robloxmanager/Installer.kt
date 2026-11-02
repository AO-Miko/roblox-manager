package app.robloxmanager

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.provider.Settings
import androidx.core.content.IntentCompat
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
    const val DEFAULT_URL = "https://raw.githubusercontent.com/AO-Miko/roblox-manager/release/dist/"      // the raw address of the repository's dist/ folder; can be changed in Settings

    /** The address saved in Settings (the stable channel's). */
    fun savedUrl(sv: Services) = sv.prefs.str("updateUrl", DEFAULT_URL)

    fun isBeta(sv: Services) = sv.prefs.str("channel", "stable") == "beta"

    /** The address to ask: on the beta channel the beta branch of the same repository. */
    fun url(sv: Services) = savedUrl(sv).let { if (isBeta(sv)) AppUpdate.betaUrl(it) else it }

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

    /** Hands the verified APK to Android's installer (a PackageInstaller session). The system asks the user to confirm (and, once, to allow installs from this app). */
    fun install(ctx: Context, apk: File): String {
        if (!ctx.packageManager.canRequestPackageInstalls()) {
            ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return "Allow installs from this app, then press Install again."
        }
        return try {
            val installer = ctx.packageManager.packageInstaller
            val id = installer.createSession(PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL))
            installer.openSession(id).use { session ->
                apk.inputStream().use { input -> session.openWrite("roblox-manager.apk", 0, apk.length()).use { out -> input.copyTo(out); session.fsync(out) } }
                val answer = PendingIntent.getBroadcast(ctx, id, Intent(ctx, InstallStatus::class.java).setPackage(ctx.packageName), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE)
                session.commit(answer.intentSender)                  // (the system sends its answer to InstallStatus)
            }
            "Installer opened."
        } catch (e: Exception) {
            "Could not start the installer: ${e.javaClass.simpleName}"
        }
    }
}

/** Receives the installer's answers: when it needs the user's confirmation it hands over the dialog to show. */
class InstallStatus : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE) != PackageInstaller.STATUS_PENDING_USER_ACTION) return
        val dialog = IntentCompat.getParcelableExtra(intent, Intent.EXTRA_INTENT, Intent::class.java) ?: return
        ctx.startActivity(dialog.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
