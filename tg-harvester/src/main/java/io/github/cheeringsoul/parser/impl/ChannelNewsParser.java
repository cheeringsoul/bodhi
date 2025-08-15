package io.github.cheeringsoul.parser.impl;

import io.github.cheeringsoul.Config;
import io.github.cheeringsoul.Utils;
import io.github.cheeringsoul.parser.MessageParser;
import io.github.cheeringsoul.parser.ParserMeta;
import io.github.cheeringsoul.pojo.*;
import org.drinkless.tdlib.TdApi;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

@ParserMeta(name = "ChannelNewsParser", description = "解析频道新闻消息")
public class ChannelNewsParser implements MessageParser<ChannelNewsEntity> {
    private final Config tgGroupConfig;
    private final ChatMessageParser chatMessageParser;

    public ChannelNewsParser(Config tgGroupConfig) {
        this.tgGroupConfig = tgGroupConfig;
        this.chatMessageParser = new ChatMessageParser(tgGroupConfig);
    }

    @Override
    public Optional<ChannelNewsEntity> parse(TdApi.Message message) {
        Optional<ChatMessageEntity> messageText = chatMessageParser.parseTextMessage(message);
        if (messageText.isPresent()) {
            ChatMessageEntity chatMessageEntity = messageText.get();
            List<LinkContent> linkContents = new ArrayList<>();
            if (tgGroupConfig.needExtractLink(message.chatId)) {
                linkContents = chatMessageEntity.urls().stream()
                        .map(url -> {
                            CrawledData crawledData = Utils.crawlUrl(url);
                            return new LinkContent(url, crawledData.title(), crawledData.content(), crawledData, chatMessageEntity.timestamp());
                        })
                        .toList();
            }
            ChannelNewsEntity channelNewsEntity = new ChannelNewsEntity(
                    message.id,
                    chatMessageEntity.chatId(),
                    tgGroupConfig.getGroupName(chatMessageEntity.chatId()),
                    chatMessageEntity.messageText(),
                    chatMessageEntity.urls(),
                    linkContents,
                    chatMessageEntity.timestamp()
            );
            return clean(message.chatId, channelNewsEntity);
        }
        return Optional.empty();
    }
}
