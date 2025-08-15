package io.github.cheeringsoul.parser;

import io.github.cheeringsoul.parser.cleaner.Cleaner;
import io.github.cheeringsoul.parser.cleaner.CleanerFactory;
import io.github.cheeringsoul.pojo.BaseEntity;
import org.drinkless.tdlib.TdApi;

import java.util.Optional;

public interface MessageParser<T extends BaseEntity> {
    Optional<T> parse(TdApi.Message message);

    default Optional<T> clean(long chatId, T entity) {
        Optional<Cleaner<T>> cleaner = CleanerFactory.INSTANCE.getCleaner(chatId);
        if (cleaner.isPresent()) {
            return cleaner.get().clean(entity);
        }
        return Optional.of(entity);
    }

}
