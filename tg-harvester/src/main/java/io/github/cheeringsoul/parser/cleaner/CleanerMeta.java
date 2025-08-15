package io.github.cheeringsoul.parser.cleaner;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface CleanerMeta {
    long chatId();

    long[] ignoredSenderId() default {};  // 忽略的发送者ID列表
}
