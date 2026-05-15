-- Жанры
CREATE TABLE genres (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

-- Лейблы
CREATE TABLE labels (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    country VARCHAR(100)
);

-- Артисты
CREATE TABLE artists (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    country VARCHAR(100),
    description TEXT
);

-- Альбомы
CREATE TABLE releases (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    artist_id INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    label_id INTEGER REFERENCES labels(id) ON DELETE SET NULL,
    release_year INTEGER CHECK (release_year >= 1900 AND release_year <= 2100),
    description TEXT, -- Добавлено описание альбома
    cover_image_url VARCHAR(500)
);

-- Связь альбомов и жанров
CREATE TABLE release_genres (
    release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    genre_id INTEGER NOT NULL REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (release_id, genre_id)
);

-- Пластинки
CREATE TABLE vinyl_records (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    sku VARCHAR(50) UNIQUE NOT NULL CHECK (length(sku) >= 10), -- Проверка формата артикула
    format VARCHAR(50) NOT NULL,
    color VARCHAR(100) DEFAULT 'Black',
    condition_media VARCHAR(50) NOT NULL,
    -- Поле condition_sleeve удалено
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Клиенты
CREATE TABLE customers (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL, 
    username VARCHAR(100) NOT NULL,     
    email VARCHAR(255),
    phone VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Заказы
CREATE TABLE orders (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    status VARCHAR(50) NOT NULL DEFAULT 'На рассмотрении', -- Обновленный дефолтный статус
    total_amount DECIMAL(10, 2) NOT NULL CHECK (total_amount >= 0),
    delivery_method VARCHAR(50) NOT NULL,
    shipping_address TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Связь заказов и пластинок
CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    vinyl_record_id INTEGER NOT NULL REFERENCES vinyl_records(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price_at_purchase DECIMAL(10, 2) NOT NULL CHECK (price_at_purchase >= 0),
    PRIMARY KEY (order_id, vinyl_record_id)
);

-- Логи заказов
CREATE TABLE order_status_log (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- Современный стандарт автоинкремента
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    old_status VARCHAR(50),
    new_status VARCHAR(50) NOT NULL,
    changed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE PROCEDURE cancel_order_and_restock(p_order_id INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_status VARCHAR(50);
    item RECORD;
BEGIN
    SELECT status INTO v_current_status FROM orders WHERE id = p_order_id;
    
    IF v_current_status = 'Отменен' THEN
        RAISE NOTICE 'Заказ % уже отменен. Отмена операции.', p_order_id;
        RETURN;
    END IF;
    
    FOR item IN SELECT vinyl_record_id, quantity FROM order_items WHERE order_id = p_order_id
    LOOP
        UPDATE vinyl_records 
        SET stock_quantity = stock_quantity + item.quantity
        WHERE id = item.vinyl_record_id;
    END LOOP;
    
    UPDATE orders SET status = 'Отменен' WHERE id = p_order_id;
END;
$$;


CREATE OR REPLACE FUNCTION get_customer_total_spent(p_telegram_id BIGINT)
RETURNS DECIMAL(10, 2) AS $$
DECLARE
    v_total DECIMAL(10, 2);
BEGIN
    -- Считаем сумму только по выполненным заказам
    SELECT COALESCE(SUM(total_amount), 0) INTO v_total
    FROM orders o
    JOIN customers c ON o.customer_id = c.id
    WHERE c.telegram_id = p_telegram_id AND o.status = 'Выполнен';
    
    RETURN v_total;
END;
$$ LANGUAGE plpgsql


CREATE OR REPLACE FUNCTION log_order_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        
        INSERT INTO order_status_log (order_id, old_status, new_status)
        VALUES (NEW.id, OLD.status, NEW.status);
        
    END IF;
    
    RETURN NEW; 
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER trg_order_status_audit
AFTER UPDATE OF status ON orders
FOR EACH ROW
EXECUTE FUNCTION log_order_status_change();


-- Ищет релизы только среди тех пластинок, которые реально есть в наличии
CREATE INDEX idx_vinyl_active_stock ON vinyl_records(release_id) WHERE stock_quantity > 0;

-- Хранит ID только тех заказов, которые нужно показать админ
CREATE INDEX idx_orders_active_only ON orders(id) WHERE status NOT IN ('Выполнен', 'Отменен');

-- Мгновенно вытаскивает все альбомы, когда покупатель нажимает на кнопку с именем исполнителя
CREATE INDEX idx_releases_artist_id ON releases(artist_id);

-- Мгновенно находит альбомы по нажатию на кнопку жанра
CREATE INDEX idx_release_genres_genre_id ON release_genres(genre_id);

-- Вытягивает историю заказов для конкретного telegram_id без сканирования чеков других людей
CREATE INDEX idx_orders_customer_id ON orders(customer_id);

-- Находит все товары, привязанные к конкретному order_id
CREATE INDEX idx_order_items_order_id ON order_items(order_id);

-- Вытаскивает нужные логи среди большого количества других
CREATE INDEX idx_order_status_log_order_id ON order_status_log(order_id);


-- Полный каталог винила, связывающий склад, альбом и артиста 
CREATE VIEW view_vinyl_catalog AS
SELECT 
    v.id AS record_id,
    v.sku,
    v.format,
    v.color,
    v.condition_media,
    v.price,
    v.stock_quantity,
    r.id AS release_id,
    r.title AS album_title,
    r.release_year,
    r.description AS album_description,
    r.cover_image_url,
    a.id AS artist_id,
    a.name AS artist_name
FROM vinyl_records v
JOIN releases r ON v.release_id = r.id
JOIN artists a ON r.artist_id = a.id;

-- Сводка по заказам (Связывает заказ и покупателя)
CREATE VIEW view_order_summary AS
SELECT 
    o.id AS order_id,
    c.telegram_id,
    c.username, 
    o.status,
    o.total_amount,
    o.delivery_method,
    o.shipping_address,
    o.created_at
FROM orders o
JOIN customers c ON o.customer_id = c.id;
-- Детализация товаров в чеке (Связывает чек, склад, альбом и артиста)
CREATE OR REPLACE VIEW view_order_items_detail AS
SELECT 
    oi.order_id,
    oi.quantity,
    oi.price_at_purchase,
    v.sku,
    v.format,
    v.color,
    r.title AS album_title,
    a.name AS artist_name
FROM order_items oi
JOIN vinyl_records v ON oi.vinyl_record_id = v.id
JOIN releases r ON v.release_id = r.id
JOIN artists a ON r.artist_id = a.id;


INSERT INTO genres (name) VALUES 
('Progressive Rock'),
('Electronic'),
('Funk'),
('Grunge'),
('Pop'),
('Hip-Hop'),
('Alternative Rock'),
('Jazz'),
('Blues'),
('Reggae');

INSERT INTO labels (name, country) VALUES
('Harvest Records', 'UK'),
('Columbia Records', 'USA'),
('Epic Records', 'USA'),
('Top Dawg Entertainment', 'USA'),
('Warner Bros. Records', 'USA'),
('Blue Note Records', 'USA'),
('DGC Records', 'USA'),
('Apple Records', 'UK'),
('EMI', 'UK'),
('Island Records', 'UK');

INSERT INTO artists (name, country, description) VALUES
('Pink Floyd', 'UK', 'Легендарная британская рок-группа.'),
('Daft Punk', 'France', 'Французский электронный дуэт.'),
('Alice in Chains', 'USA', 'Иконы гранж-сцены из Сиэтла с неповторимым мрачным звучанием.'),
('Michael Jackson', 'USA', 'Король поп-музыки, перевернувший индустрию.'),
('Kendrick Lamar', 'USA', 'Один из самых влиятельных и техничных хип-хоп исполнителей современности.'),
('Red Hot Chili Peppers', 'USA', 'Легенды калифорнийского альтернативного рока и фанка.'),
('Miles Davis', 'USA', 'Величайший джазовый трубач и композитор.'),
('Nirvana', 'USA', 'Культовая гранж-группа 90-х из Сиэтла.'),
('The Beatles', 'UK', 'Самая влиятельная музыкальная группа в истории.'),
('Bob Marley', 'Jamaica', 'Король регги и популяризатор ямайской культуры.');


-- Добавляем альбомы

INSERT INTO releases (title, artist_id, label_id, release_year, description, cover_image_url) VALUES
('The Dark Side of the Moon', (SELECT id FROM artists WHERE name = 'Pink Floyd'), (SELECT id FROM labels WHERE name = 'Harvest Records'), 1973, 'Культовый альбом о жизни, времени и безумии.', 'static/dsotm.jpg'),
('Random Access Memories', (SELECT id FROM artists WHERE name = 'Daft Punk'), (SELECT id FROM labels WHERE name = 'Columbia Records'), 2013, 'Последний студийный альбом дуэта.', 'static/ram.jpg'),
('Dirt', (SELECT id FROM artists WHERE name = 'Alice in Chains'), (SELECT id FROM labels WHERE name = 'Columbia Records'), 1992, 'Мрачный и тяжелый шедевр гранжа.', 'static/Alice_in_Chains-Dirt.jpg'),
('Thriller', (SELECT id FROM artists WHERE name = 'Michael Jackson'), (SELECT id FROM labels WHERE name = 'Epic Records'), 1982, 'Самый продаваемый альбом всех времен.', 'static/thriller.jpg'),
('To Pimp a Butterfly', (SELECT id FROM artists WHERE name = 'Kendrick Lamar'), (SELECT id FROM labels WHERE name = 'Top Dawg Entertainment'), 2015, 'Музыкальный и культурный хип-хоп шедевр десятилетия.', 'static/tpab.jpg'),
('Californication', (SELECT id FROM artists WHERE name = 'Red Hot Chili Peppers'), (SELECT id FROM labels WHERE name = 'Warner Bros. Records'), 1999, 'Триумфальное возвращение RHCP к вершинам чартов.', 'static/californication.jpg'),
('Kind of Blue', (SELECT id FROM artists WHERE name = 'Miles Davis'), (SELECT id FROM labels WHERE name = 'Blue Note Records'), 1959, 'Самый популярный джазовый альбом в мире.', 'static/kob.jpg'),
('Nevermind', (SELECT id FROM artists WHERE name = 'Nirvana'), (SELECT id FROM labels WHERE name = 'DGC Records'), 1991, 'Альбом, перевернувший музыкальную индустрию 90-х.', 'static/nevermind.jpg'),
('Abbey Road', (SELECT id FROM artists WHERE name = 'The Beatles'), (SELECT id FROM labels WHERE name = 'Apple Records'), 1969, 'Последний совместно записанный шедевр.', 'static/ar.jpg'),
('Legend', (SELECT id FROM artists WHERE name = 'Bob Marley'), (SELECT id FROM labels WHERE name = 'Island Records'), 1984, 'Сборник лучших хитов Боба Марли.', 'static/legend.jpg');


-- Связываем альбомы и жанры

INSERT INTO release_genres (release_id, genre_id) VALUES
((SELECT id FROM releases WHERE title = 'The Dark Side of the Moon'), (SELECT id FROM genres WHERE name = 'Progressive Rock')),
((SELECT id FROM releases WHERE title = 'Random Access Memories'), (SELECT id FROM genres WHERE name = 'Electronic')),
((SELECT id FROM releases WHERE title = 'Random Access Memories'), (SELECT id FROM genres WHERE name = 'Funk')),
((SELECT id FROM releases WHERE title = 'Dirt'), (SELECT id FROM genres WHERE name = 'Grunge')),
((SELECT id FROM releases WHERE title = 'Thriller'), (SELECT id FROM genres WHERE name = 'Pop')),
((SELECT id FROM releases WHERE title = 'To Pimp a Butterfly'), (SELECT id FROM genres WHERE name = 'Hip-Hop')),
((SELECT id FROM releases WHERE title = 'Californication'), (SELECT id FROM genres WHERE name = 'Alternative Rock')),
((SELECT id FROM releases WHERE title = 'Californication'), (SELECT id FROM genres WHERE name = 'Funk')),
((SELECT id FROM releases WHERE title = 'Kind of Blue'), (SELECT id FROM genres WHERE name = 'Jazz')),
((SELECT id FROM releases WHERE title = 'Nevermind'), (SELECT id FROM genres WHERE name = 'Grunge')),
((SELECT id FROM releases WHERE title = 'Nevermind'), (SELECT id FROM genres WHERE name = 'Alternative Rock')),
((SELECT id FROM releases WHERE title = 'Abbey Road'), (SELECT id FROM genres WHERE name = 'Pop')),
((SELECT id FROM releases WHERE title = 'Legend'), (SELECT id FROM genres WHERE name = 'Reggae'));

-- Расписываем пластинки

INSERT INTO vinyl_records (release_id, sku, format, color, condition_media, price, stock_quantity) VALUES
((SELECT id FROM releases WHERE title = 'The Dark Side of the Moon'), 'VIN-12-PF001', '12" LP', 'Black', 'Mint', 3500.00, 5),
((SELECT id FROM releases WHERE title = 'The Dark Side of the Moon'), 'VIN-12-PF002', '12" LP', 'Transparent', 'VG+', 2500.00, 2),
((SELECT id FROM releases WHERE title = 'Random Access Memories'), 'VIN-12-DP001', '2xLP', '180g Black', 'Mint', 4500.00, 10),
((SELECT id FROM releases WHERE title = 'Dirt'), 'VIN-12-AIC92', '12" LP', 'Black', 'Mint', 4200.00, 3),
((SELECT id FROM releases WHERE title = 'Thriller'), 'VIN-12-MJT82', '12" LP', 'Red Translucent', 'NM', 3500.00, 5),
((SELECT id FROM releases WHERE title = 'To Pimp a Butterfly'), 'VIN-12-KL015', '2xLP', 'Black', 'Mint', 5500.00, 10),
((SELECT id FROM releases WHERE title = 'Californication'), 'VIN-12-RHC99', '2xLP', 'Purple', 'Mint', 4800.00, 4),
((SELECT id FROM releases WHERE title = 'Kind of Blue'), 'VIN-12-MD059', '12" LP', 'Blue', 'Mint', 3200.00, 12),
((SELECT id FROM releases WHERE title = 'Nevermind'), 'VIN-12-NV091', '12" LP', 'Silver', 'NM', 4000.00, 6),
((SELECT id FROM releases WHERE title = 'Abbey Road'), 'VIN-12-AR069', '12" LP', 'Black', 'Mint', 3800.00, 15),
((SELECT id FROM releases WHERE title = 'Legend'), 'VIN-12-BM084', '12" LP', 'Yellow/Green', 'Mint', 3000.00, 8);

-- Регистрируем клиентов

INSERT INTO customers (username, email, phone, telegram_id) VALUES
('ivan_vinyl', 'ivan.vinyl@mail.ru', '+79991234567', 100000001),
('anna_music', 'anna_music@gmail.com', '+79001112233', 100000002),
('petr_v_88', 'petr.v@example.com', '+79002223344', 100000003),
('elena_moroz', 'elena.m@example.com', '+79003334455', 100000004),
('serg_pavlov', 'serg.p@example.com', '+79004445566', 100000005),
('mary_wolf', 'maria.v@example.com', '+79005556677', 100000006),
('dimon_sokol', 'dmitry.s@example.com', '+79006667788', 100000007),
('olga_leb', 'olga.l@example.com', '+79007778899', 100000008),
('alex_nov', 'alex.n@example.com', '+79008889900', 100000009),
('tanya_kozlova', 'tanya.k@example.com', '+79009990011', 100000010);

-- Оформляем заказы и чеки

INSERT INTO orders (customer_id, status, total_amount, delivery_method, shipping_address) VALUES
((SELECT id FROM customers WHERE telegram_id = 100000001), 'Выполнен', 7000.00, 'Доставка', 'г. Москва, ул. Виниловая, д. 33, кв. 1'),
((SELECT id FROM customers WHERE telegram_id = 100000002), 'Оплачен', 4500.00, 'Самовывоз', NULL),
((SELECT id FROM customers WHERE telegram_id = 100000003), 'На рассмотрении', 3200.00, 'Доставка', 'г. Питер, Невский пр. 10'),
((SELECT id FROM customers WHERE telegram_id = 100000004), 'Отменен', 4000.00, 'Самовывоз', NULL),
((SELECT id FROM customers WHERE telegram_id = 100000005), 'Отправлен', 3800.00, 'Доставка', 'г. Казань, ул. Баумана 5'),
((SELECT id FROM customers WHERE telegram_id = 100000006), 'Выполнен', 3000.00, 'Доставка', 'г. Сочи, ул. Морская 12'),
((SELECT id FROM customers WHERE telegram_id = 100000007), 'На рассмотрении', 8000.00, 'Доставка', 'г. Новосибирск, Красный пр. 1'),
((SELECT id FROM customers WHERE telegram_id = 100000008), 'Оплачен', 3500.00, 'Самовывоз', NULL),
((SELECT id FROM customers WHERE telegram_id = 100000009), 'Выполнен', 5500.00, 'Доставка', 'г. Екатеринбург, ул. Малышева 12'),
((SELECT id FROM customers WHERE telegram_id = 100000010), 'Отправлен', 4800.00, 'Самовывоз', NULL);

INSERT INTO order_items (order_id, vinyl_record_id, quantity, price_at_purchase) VALUES
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000001) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-PF002'), 1, 2500.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000001) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-DP001'), 1, 4500.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000002) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-DP001'), 1, 4500.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000003) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-MD059'), 1, 3200.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000004) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-NV091'), 1, 4000.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000005) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-AR069'), 1, 3800.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000006) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-BM084'), 1, 3000.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000007) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-NV091'), 2, 4000.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000008) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-MJT82'), 1, 3500.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000009) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-KL015'), 1, 5500.00),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000010) LIMIT 1), (SELECT id FROM vinyl_records WHERE sku = 'VIN-12-RHC99'), 1, 4800.00);


-- Логи заказов

INSERT INTO order_status_log (order_id, old_status, new_status, changed_at) VALUES
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000001) LIMIT 1), 'На рассмотрении', 'Оплачен', NOW() - INTERVAL '5 days'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000001) LIMIT 1), 'Оплачен', 'Отправлен', NOW() - INTERVAL '4 days'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000001) LIMIT 1), 'Отправлен', 'Выполнен', NOW() - INTERVAL '2 days'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000002) LIMIT 1), 'На рассмотрении', 'Оплачен', NOW() - INTERVAL '1 day'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000004) LIMIT 1), 'На рассмотрении', 'Отменен', NOW() - INTERVAL '3 days'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000005) LIMIT 1), 'На рассмотрении', 'Оплачен', NOW() - INTERVAL '4 days'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000005) LIMIT 1), 'Оплачен', 'Отправлен', NOW() - INTERVAL '1 day'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000006) LIMIT 1), 'На рассмотрении', 'Оплачен', NOW() - INTERVAL '10 days'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000006) LIMIT 1), 'Оплачен', 'Отправлен', NOW() - INTERVAL '8 days'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000006) LIMIT 1), 'Отправлен', 'Выполнен', NOW() - INTERVAL '5 days'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000009) LIMIT 1), 'На рассмотрении', 'Оплачен', NOW() - INTERVAL '7 days'),
((SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE telegram_id = 100000009) LIMIT 1), 'Оплачен', 'Выполнен', NOW() - INTERVAL '6 days');
