\connect smoke_db
CREATE TABLE IF NOT EXISTS public.orders (
    id integer NOT NULL PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(10,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS public.orders_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.orders_id_seq OWNED BY public.orders.id;
ALTER TABLE ONLY public.orders ALTER COLUMN id SET DEFAULT nextval('public.orders_id_seq'::regclass);
INSERT INTO public.orders (id, customer_name, amount, created_at) VALUES
    (1, 'alice', 12.50, '2026-03-21 00:22:48.36938+00'),
    (2, 'bob', 34.20, '2026-03-21 00:22:48.377983+00')
ON CONFLICT (id) DO NOTHING;
SELECT setval('public.orders_id_seq', 2, true);
ALTER TABLE public.orders OWNER TO smoke;
GRANT ALL ON ALL TABLES IN SCHEMA public TO smoke;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO smoke;

\connect demo
CREATE TABLE IF NOT EXISTS public.orders (
    id integer NOT NULL PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(10,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS public.orders_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.orders_id_seq OWNED BY public.orders.id;
ALTER TABLE ONLY public.orders ALTER COLUMN id SET DEFAULT nextval('public.orders_id_seq'::regclass);
INSERT INTO public.orders (id, customer_name, amount, created_at) VALUES
    (1, 'alice', 12.50, '2026-03-21 00:22:48.36938+00'),
    (2, 'bob', 34.20, '2026-03-21 00:22:48.377983+00')
ON CONFLICT (id) DO NOTHING;
SELECT setval('public.orders_id_seq', 2, true);
ALTER TABLE public.orders OWNER TO demo;
GRANT ALL ON ALL TABLES IN SCHEMA public TO demo;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO demo;
GRANT USAGE ON SCHEMA public TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO readonly;
GRANT USAGE ON SCHEMA public TO writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO writer;
