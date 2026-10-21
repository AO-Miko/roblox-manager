# kotlinx.serialization keeps what it needs through its own consumer rules; OkHttp/Okio ship theirs too.
-keepattributes *Annotation*, InnerClasses
-dontwarn org.bouncycastle.**
-dontwarn org.conscrypt.**
-dontwarn org.openjsse.**
