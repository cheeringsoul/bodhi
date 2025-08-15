package io.github.cheeringsoul;

import io.github.cheeringsoul.dao.TgRepository;
import io.github.cheeringsoul.pojo.BaseEntity;
import io.github.cheeringsoul.pojo.ChannelNewsEntity;
import io.github.cheeringsoul.pojo.ChatMessageEntity;
import io.github.cheeringsoul.pojo.LinkContent;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MessageSaver {
    public static final MessageSaver INSTANCE = new MessageSaver();
    private final ExecutorService executorService = Executors.newSingleThreadExecutor();

    private MessageSaver() {
    }

    public void save(BaseEntity entity) {
        if (entity instanceof ChatMessageEntity chatMessage) {
            saveChatMessage(chatMessage);
        } else if (entity instanceof ChannelNewsEntity channelNewsEntity) {
            saveChannelNews(channelNewsEntity);
        } else {
            throw new IllegalArgumentException("Unsupported entity type: " + entity.getClass().getName());
        }
    }

    private void saveChatMessage(ChatMessageEntity chatMessage) {
        executorService.execute(() -> TgRepository.insertChatMessage(chatMessage));
    }

    private void saveChannelNews(ChannelNewsEntity channelNewsEntity) {
        executorService.execute(() -> {
            long id = TgRepository.insertChannelNews(channelNewsEntity);

            for (LinkContent content : channelNewsEntity.linkContents()) {
                TgRepository.insertLinkPage(id, content);
            }
        });
    }

}
