package app.robloxmanager.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive

/** What changed in one version. The log ships inside the app (assets/changelog.json), so it always describes the installed build. */
data class ChangelogEntry(val version: String, val date: String, val changes: List<String>)

object Changelog {
    /** Newest first. A missing or damaged file gives an empty list. */
    fun parse(text: String): List<ChangelogEntry> {
        val arr = try { AppJson.parseToJsonElement(text) as? JsonArray } catch (_: Exception) { null } ?: return emptyList()
        return arr.mapNotNull { e ->
            val o = e.obj ?: return@mapNotNull null
            val v = o.str("version")?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            ChangelogEntry(v, o.str("date") ?: "", o.arr("changes").orEmpty().mapNotNull { (it as? JsonPrimitive)?.content?.trim() }.filter { it.isNotEmpty() })
        }
    }
}
