package io.github.cheeringsoul.parser;

import io.github.cheeringsoul.Config;
import io.github.cheeringsoul.pojo.*;
import lombok.Setter;
import lombok.extern.slf4j.Slf4j;
import org.drinkless.tdlib.TdApi;
import org.reflections.Reflections;
import org.reflections.scanners.Scanners;
import org.reflections.util.ConfigurationBuilder;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.*;
import java.util.function.BiPredicate;
import java.util.stream.Collectors;

import static io.github.cheeringsoul.Utils.getSenderUserId;

@Slf4j
public class ParserFactory {
    private final Config tgGroupConfig;
    private final Map<String, MessageParser<? extends BaseEntity>> parserMap = new HashMap<>();

    @Setter
    private BiPredicate<Long, Long> ignoreSender = (chatId, senderId) -> false;

    public ParserFactory(Config tgGroupConfig) {
        this.tgGroupConfig = tgGroupConfig;
        loadParser();
    }

    public ParserFactory(Config tgGroupConfig, BiPredicate<Long, Long> ignoreSender) {
        this.tgGroupConfig = tgGroupConfig;
        this.ignoreSender = ignoreSender;
        loadParser();
    }

    private void loadParser() {
        String parserImplPkg = System.getProperty("message.parser.impl.package", "io.github.cheeringsoul.parser.impl");
        Reflections reflections = new Reflections(new ConfigurationBuilder()
                .forPackage(parserImplPkg)
                .addScanners(Scanners.SubTypes, Scanners.TypesAnnotated));
        @SuppressWarnings("rawtypes") Set<Class<? extends MessageParser>> subTypes = reflections.getSubTypesOf(MessageParser.class);
        Set<Class<?>> annotatedClasses = reflections.get(Scanners.TypesAnnotated.with(ParserMeta.class).asClass());
        Set<Class<?>> result = subTypes.stream().filter(annotatedClasses::contains).collect(Collectors.toSet());
        for (Class<?> clazz : result) {
            MessageParser<? extends BaseEntity> parser;
            ParserMeta meta = clazz.getAnnotation(ParserMeta.class);
            try {
                parser = (MessageParser<? extends BaseEntity>) clazz.getDeclaredConstructor(Config.class).newInstance(tgGroupConfig);
            } catch (InstantiationException | IllegalAccessException | InvocationTargetException |
                     NoSuchMethodException e) {
                throw new RuntimeException(e);
            }
            var parserProxy = (MessageParser<? extends BaseEntity>) Proxy.newProxyInstance(
                    clazz.getClassLoader(),
                    clazz.getInterfaces(),
                    (proxy, method, args) -> {
                        if (method.getDeclaringClass().equals(MessageParser.class)) {
                            TdApi.Message message = (TdApi.Message) args[0];
                            // 忽略机器人消息
                            if (ignoreSender.test(message.chatId, getSenderUserId(message.senderId))) {
                                log.debug("Ignoring message from bot: chatId={}, senderId={}", message.chatId, getSenderUserId(message.senderId));
                                return Optional.empty();
                            }
                        }
                        return method.invoke(parser, args);
                    }
            );
            parserMap.put(meta.name(), parserProxy);

        }
    }

    public Optional<MessageParser<? extends BaseEntity>> getParser(long chatId) {
        String parserName = tgGroupConfig.getParserName(chatId);
        if (parserName == null) {
            log.warn("No parser configured for chatId: {}", chatId);
            return Optional.empty();
        }
        MessageParser<? extends BaseEntity> parser = parserMap.get(parserName);
        if (parser == null) {
            log.warn("No parser found for chatId: {}", chatId);
            return Optional.empty();
        }
        return Optional.of(parser);
    }
}
