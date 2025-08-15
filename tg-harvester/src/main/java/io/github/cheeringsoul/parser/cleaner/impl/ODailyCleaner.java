package io.github.cheeringsoul.parser.cleaner.impl;

import io.github.cheeringsoul.parser.cleaner.Cleaner;
import io.github.cheeringsoul.parser.cleaner.CleanerMeta;
import io.github.cheeringsoul.pojo.ChannelNewsEntity;
import io.github.cheeringsoul.pojo.LinkContent;
import lombok.extern.slf4j.Slf4j;

import java.util.Optional;

@Slf4j
@CleanerMeta(chatId = -1001525105897L)
public class ODailyCleaner implements Cleaner<ChannelNewsEntity> {
    @Override
    public Optional<ChannelNewsEntity> clean(ChannelNewsEntity entity) {
        for (LinkContent item: entity.linkContents()) {
            if (item.crawledData().doc() == null) {
                continue;
            }
            String text = item.crawledData().doc().select("._4z3rUROM").text().trim();
            if (text.isEmpty()) {
                log.warn("[Ignore message] ODaily content is empty url {}", item.url());
                continue;
            }
            if (text.contains("金十")) {
                // 内容转载自金十数据
                log.debug("[Ignore message] ODaily message content contains 金十 url {}, ignore", item.url());
                continue;
            }
            item.content(text);
        }
        return Optional.of(entity);
    }
}
