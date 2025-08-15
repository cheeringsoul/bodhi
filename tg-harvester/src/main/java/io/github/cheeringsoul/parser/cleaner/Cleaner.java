package io.github.cheeringsoul.parser.cleaner;

import io.github.cheeringsoul.pojo.BaseEntity;

import java.util.Optional;

public interface Cleaner<T extends BaseEntity> {
    Optional<T> clean(T entity);
}
