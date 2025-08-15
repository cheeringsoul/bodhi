package io.github.cheeringsoul.parser.impl;

import io.github.cheeringsoul.Config;
import io.github.cheeringsoul.parser.MessageParser;
import io.github.cheeringsoul.parser.ParserMeta;
import io.github.cheeringsoul.pojo.ChatMessageEntity;
import org.apache.commons.lang3.StringUtils;
import org.drinkless.tdlib.TdApi;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

import static io.github.cheeringsoul.Utils.getSenderUserId;

@ParserMeta(name = "ChatMessageParser", description = "解析聊天群消息")
public class ChatMessageParser implements MessageParser<ChatMessageEntity> {
    private final Config tgGroupConfig;

    public ChatMessageParser(Config tgGroupConfig) {
        this.tgGroupConfig = tgGroupConfig;
    }

    @Override
    public Optional<ChatMessageEntity> parse(TdApi.Message message) {
        Optional<ChatMessageEntity> textMessage = parseTextMessage(message);
        if (textMessage.isPresent()) {
            return clean(message.chatId, textMessage.get());
        }
        return parseOtherMsg(message);
    }

    public Optional<ChatMessageEntity> parseTextMessage(TdApi.Message message) {
        long chatId = message.chatId;
        long senderUserId = getSenderUserId(message.senderId);
        Instant instant = Instant.ofEpochSecond(message.date);
        if (message.content instanceof TdApi.MessageText textMessage) {
            List<String> urls = new ArrayList<>();
            TdApi.FormattedText formattedText = textMessage.text;
            for (TdApi.TextEntity entity : formattedText.entities) {
                if (entity.type instanceof TdApi.TextEntityTypeTextUrl textUrl) {
                    urls.add(textUrl.url);
                } else if (entity.type instanceof TdApi.TextEntityTypeUrl) {
                    urls.add(formattedText.text.substring(entity.offset, entity.offset + entity.length));
                }
            }
            String text = StringUtils.normalizeSpace(formattedText.text.trim());
            if (Objects.equals(text, "") && urls.isEmpty()) {
                return Optional.empty();
            }
            return Optional.of(new ChatMessageEntity(message.id, chatId, senderUserId, tgGroupConfig.getGroupName(chatId), text, urls, instant));
        }
        return Optional.empty();
    }

    private Optional<ChatMessageEntity> parseOtherMsg(TdApi.Message message) {
        String text = switch (message.content) {
            case TdApi.MessagePhoto ignored -> "[picture]";
            case TdApi.MessageVideo ignored -> "[video]";
            case TdApi.MessageVoiceNote ignored -> "[voice note]";
            case TdApi.MessageAnimation ignored -> "[animation]";
            case TdApi.MessageAudio ignored -> "[audio]";
            case TdApi.MessageSticker ignored -> "[sticker]";
            case TdApi.MessageDocument ignored -> "[document]";
            case TdApi.MessageLocation ignored -> "[location]";
            case TdApi.MessageVenue ignored -> "[venue]";
            case TdApi.MessageContact ignored -> "[contact]";
            default -> null;
        };
        if (text != null) {
            long chatId = message.chatId;
            long senderUserId = getSenderUserId(message.senderId);
            Instant instant = Instant.ofEpochSecond(message.date);
            ChatMessageEntity chatMessageEntity = new ChatMessageEntity(
                    message.id,
                    chatId,
                    senderUserId,
                    tgGroupConfig.getGroupName(chatId),
                    text,
                    List.of(),
                    instant
            );
            return Optional.of(chatMessageEntity);
        }
        return Optional.empty();
    }
}
