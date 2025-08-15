package io.github.cheeringsoul.parser.cleaner;

import io.github.cheeringsoul.pojo.BaseEntity;
import org.reflections.Reflections;
import org.reflections.scanners.Scanners;
import org.reflections.util.ConfigurationBuilder;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.*;
import java.util.stream.Collectors;

public class CleanerFactory {
    private final Map<Long, Cleaner<? extends BaseEntity>> cleaners = new HashMap<>();
    public static CleanerFactory INSTANCE = new CleanerFactory();

    private CleanerFactory() {
        this.init();
    }

    private void init() {
        String parserImplPkg = System.getProperty("message.cleaner.impl.package", "io.github.cheeringsoul.parser.cleaner.impl");
        Reflections reflections = new Reflections(new ConfigurationBuilder()
                .forPackage(parserImplPkg)
                .addScanners(Scanners.SubTypes, Scanners.TypesAnnotated));
        @SuppressWarnings("rawtypes") Set<Class<? extends Cleaner>> subTypes = reflections.getSubTypesOf(Cleaner.class);
        Set<Class<?>> annotatedClasses = reflections.get(Scanners.TypesAnnotated.with(CleanerMeta.class).asClass());
        Set<Class<?>> result = subTypes.stream().filter(annotatedClasses::contains).collect(Collectors.toSet());
        for (Class<?> clazz : result) {
            final Cleaner<? extends BaseEntity> cleaner;
            CleanerMeta meta = clazz.getAnnotation(CleanerMeta.class);
            if (meta != null) {
                long chatId = meta.chatId();
                long[] ignoreSenderId = meta.ignoredSenderId();
                Set<Long> ignoredSenderIdSet = Arrays.stream(ignoreSenderId).boxed().collect(Collectors.toSet());
                try {
                    cleaner = (Cleaner<? extends BaseEntity>) clazz.getDeclaredConstructor().newInstance();
                } catch (InstantiationException | IllegalAccessException | InvocationTargetException |
                         NoSuchMethodException e) {
                    throw new RuntimeException(e);
                }
                var cleanerProxy = (Cleaner<? extends BaseEntity>) Proxy.newProxyInstance(
                        clazz.getClassLoader(),
                        clazz.getInterfaces(),
                        (proxy, method, args) -> {
                            if (method.getDeclaringClass().equals(Cleaner.class)) {
                                BaseEntity entity = (BaseEntity) args[0];
                                // 忽略指定userId消息
                                if (ignoredSenderIdSet.contains(entity.senderId())) {
                                    return Optional.empty();
                                }
                            }
                            return method.invoke(cleaner, args);
                        }
                );
                cleaners.put(chatId, cleanerProxy);
            } else {
                throw new RuntimeException("Cleaner class " + clazz.getName() + " is missing CleanerMeta annotation");
            }
        }
    }

    public <T extends BaseEntity> Optional<Cleaner<T>> getCleaner(long chatId) {
        Cleaner<? extends BaseEntity> cleaner = cleaners.get(chatId);
        if (cleaner == null) {
            return Optional.empty();
        }
        @SuppressWarnings("unchecked")
        Cleaner<T> typedCleaner = (Cleaner<T>) cleaner;
        return Optional.of(typedCleaner);
    }
}
