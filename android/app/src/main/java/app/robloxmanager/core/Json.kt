package app.robloxmanager.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull

/** Roblox's answers vary a lot between routes, so they are read as trees with forgiving accessors instead of fixed classes. */
val AppJson = Json { ignoreUnknownKeys = true; isLenient = true; encodeDefaults = true; prettyPrint = false }

val JsonElement?.obj: JsonObject? get() = this as? JsonObject
val JsonElement?.arr: JsonArray? get() = this as? JsonArray
val JsonElement?.text: String? get() = (this as? JsonPrimitive)?.takeIf { it.isString || it.contentOrNull != null }?.contentOrNull

fun JsonObject.str(key: String): String? = (this[key] as? JsonPrimitive)?.contentOrNull?.takeIf { this[key] !is kotlinx.serialization.json.JsonNull }
fun JsonObject.long(key: String): Long? = (this[key] as? JsonPrimitive)?.let { it.longOrNull ?: it.doubleOrNull?.toLong() }
fun JsonObject.int(key: String): Int? = long(key)?.toInt()
fun JsonObject.bool(key: String): Boolean? = (this[key] as? JsonPrimitive)?.booleanOrNull
fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject
fun JsonObject.arr(key: String): JsonArray? = this[key] as? JsonArray

/** The items of a Roblox list answer: {"data": [...]} (or a bare list). */
fun JsonElement?.items(): List<JsonObject> = when (this) {
    is JsonArray -> this.mapNotNull { it as? JsonObject }
    is JsonObject -> (this["data"] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: emptyList()
    else -> emptyList()
}

fun obj(vararg pairs: Pair<String, Any?>): JsonObject = JsonObject(pairs.filter { it.second != null }.associate { (k, v) -> k to v.toJson() })

fun Any?.toJson(): JsonElement = when (this) {
    null -> kotlinx.serialization.json.JsonNull
    is JsonElement -> this
    is String -> JsonPrimitive(this)
    is Boolean -> JsonPrimitive(this)
    is Int -> JsonPrimitive(this)
    is Long -> JsonPrimitive(this)
    is Double -> JsonPrimitive(this)
    is Collection<*> -> JsonArray(this.map { it.toJson() })
    else -> JsonPrimitive(this.toString())
}
