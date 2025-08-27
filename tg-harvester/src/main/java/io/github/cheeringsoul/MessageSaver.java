package io.github.cheeringsoul;

import io.github.cheeringsoul.dao.TgRepository;
import io.github.cheeringsoul.pojo.*;
import lombok.Getter;

import java.time.Instant;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public enum MessageSaver {
     INSTANCE;

    private final ExecutorService executorService = Executors.newFixedThreadPool(2);
    @Getter
    private Instant lastSaveTime = Instant.now();


    public void save(BaseEntity entity) {
        if (entity instanceof ChatMessageEntity chatMessage) {
            saveChatMessage(chatMessage);
        } else if (entity instanceof ChannelNewsEntity channelNewsEntity) {
            saveChannelNews(channelNewsEntity);
        } else {
            throw new IllegalArgumentException("Unsupported entity type: " + entity.getClass().getName());
        }
        lastSaveTime = Instant.now();
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

    public void saveImpression(Impression impression) {
        executorService.execute(() -> TgRepository.insertImpression(impression));
    }

    public void removeBotMessages(long chatId, long botId) {
        executorService.execute(() -> TgRepository.removeBotMessages(chatId, botId));
    }

}
