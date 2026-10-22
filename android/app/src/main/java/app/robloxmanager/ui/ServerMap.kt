package app.robloxmanager.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import app.robloxmanager.core.Place
import app.robloxmanager.core.WorldMap
import kotlin.math.hypot
import kotlin.math.min
import kotlin.math.sqrt

/** A world map with a dot for every place that has servers (bigger for more servers). Pressing a dot gives the ids of the servers there; [chosen] is the dot that is open. */
@Composable
fun ServerMap(groups: List<Pair<Place, List<String>>>, chosen: List<String>?, onPick: (List<String>) -> Unit) {
    val ctx = LocalContext.current
    val density = LocalDensity.current.density
    val land = remember { WorldMap.parseLand(try { ctx.assets.open("world_land.json").bufferedReader().use { it.readText() } } catch (_: Exception) { "" }) }
    fun radius(ids: List<String>) = (5 + min(sqrt(ids.size.toDouble()) * 1.5, 9.0)).toFloat() * density

    Canvas(
        Modifier.fillMaxWidth().aspectRatio(2f).clip(RoundedCornerShape(12.dp)).background(C.surface).pointerInput(groups) {
            detectTapGestures { pos ->
                val w = size.width.toFloat(); val h = size.height.toFloat()
                val hit = groups.minByOrNull { (p, _) -> val (x, y) = WorldMap.project(p.lat, p.lon, w, h); hypot(pos.x - x, pos.y - y) }
                if (hit != null) {
                    val (x, y) = WorldMap.project(hit.first.lat, hit.first.lon, w, h)
                    if (hypot(pos.x - x, pos.y - y) <= radius(hit.second) + 14 * density) onPick(hit.second)
                }
            }
        },
    ) {
        val w = size.width; val h = size.height
        for (lon in -150..150 step 30) { val (x, _) = WorldMap.project(0.0, lon.toDouble(), w, h); drawLine(C.surface3, Offset(x, 0f), Offset(x, h), 1f) }
        for (lat in -60..60 step 30) { val (_, y) = WorldMap.project(lat.toDouble(), 0.0, w, h); drawLine(C.surface3, Offset(0f, y), Offset(w, y), 1f) }
        val path = Path().apply {
            fillType = PathFillType.EvenOdd
            land.forEach { ring ->
                ring.forEachIndexed { i, (lon, lat) -> val (x, y) = WorldMap.project(lat, lon, w, h); if (i == 0) moveTo(x, y) else lineTo(x, y) }
                close()
            }
        }
        drawPath(path, C.surface3)
        drawPath(path, Color(0xFF3A4152), style = Stroke(1f))
        groups.forEach { (p, ids) ->
            val (x, y) = WorldMap.project(p.lat, p.lon, w, h)
            val on = chosen != null && chosen == ids
            drawCircle(if (on) Color.White else C.bg, radius(ids) + (if (on) 2f else 1.2f) * density, Offset(x, y))
            drawCircle(C.accent, radius(ids), Offset(x, y))
        }
    }
}
