package app.robloxmanager.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.core.Legal

/**
 * The question an account is asked at its first sign-in (and when the texts change): accept the Terms of use and the Privacy
 * policy, or the account is signed out. Closing the window (Back) counts as declining.
 */
@Composable
fun LegalDialog(accountName: String, onAnswer: (Boolean) -> Unit) {
    val ctx = LocalContext.current
    var ticked by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = { onAnswer(false) },
        title = { Text("Before you start, @$accountName") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("To use Roblox Manager with this account you need to accept its Terms of use and its Privacy policy. You are asked once for each account, and again if the texts change.", fontSize = 13.sp, color = C.text)
                Text("In short: it is an unofficial hobby project, not made by Roblox. Everything it keeps stays on your phone, nothing is sent to its maker, and it only talks to Roblox and GitHub (and two optional services if you turn them on). You use it at your own risk, and abusing it or the project gets your Roblox account banned from it.", fontSize = 13.sp, color = C.muted)
                Text("If you do not accept, this account is signed out (its saved sign-in is kept, and you are asked again next time).", fontSize = 13.sp, color = C.muted)
                Row { TextButton(onClick = { openUrl(ctx, Legal.TERMS_URL) }) { Text("Read the Terms of use") } }
                Row { TextButton(onClick = { openUrl(ctx, Legal.PRIVACY_URL) }) { Text("Read the Privacy policy") } }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = ticked, onCheckedChange = { ticked = it })
                    Text("I have read and I accept the Terms of use and the Privacy policy", fontSize = 13.sp, color = C.text)
                }
                Spacer(Modifier.height(2.dp))
            }
        },
        confirmButton = { TextButton(enabled = ticked, onClick = { onAnswer(true) }) { Text("Accept and continue") } },
        dismissButton = { TextButton(onClick = { onAnswer(false) }) { Text("Decline and sign out") } },
    )
}
