package app.robloxmanager.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.robloxmanager.Services
import app.robloxmanager.core.Look

val THEME_NAMES = listOf("dark" to "Dark", "light" to "Light", "system" to "Match my phone")
val SIZE_NAMES = mapOf(90 to "Small", 100 to "Normal", 110 to "Large", 125 to "Extra large")

/** Settings > Looks: the theme, the accent colour and the text size. The change shows at once and is remembered. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun LooksSection(sv: Services) {
    val look by sv.look.collectAsState()
    Section("LOOKS", collapsible = true) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Theme", color = C.muted, fontSize = 12.sp)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                THEME_NAMES.forEach { (mode, name) ->
                    FilterChip(selected = look.mode == mode, onClick = { sv.setLook(look.copy(mode = mode)) }, label = { Text(name) })
                }
            }
            Text("Accent colour", color = C.muted, fontSize = 12.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Look.ACCENTS.forEach { name ->
                    val on = look.accent == name
                    val fill = Color(Look.palette(C.dark, name).getValue("fill"))
                    androidx.compose.foundation.layout.Box(
                        Modifier.size(38.dp).clip(CircleShape).background(fill).border(if (on) 3.dp else 1.dp, if (on) C.text else C.border2, CircleShape)
                            .clickable { sv.setLook(look.copy(accent = name)) }
                            .semantics { contentDescription = "Accent colour $name"; selected = on },
                    )
                }
            }
            Text("Text size", color = C.muted, fontSize = 12.sp)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SIZE_NAMES.forEach { (size, name) ->
                    FilterChip(selected = look.size == size, onClick = { sv.setLook(look.copy(size = size)) }, label = { Text(name) })
                }
            }
            Text("The change shows at once. \"Match my phone\" follows the phone's own dark mode.", color = C.muted, fontSize = 12.sp)
        }
    }
}
