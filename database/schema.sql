--
-- PostgreSQL database dump
--

\restrict LpxFwdW5QSaiIVt7IOYUQzuK9i4tABzA0hF2nd6Gn1F2GgccKwmxbkcbNRJSExj

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: record_mes_progress(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.record_mes_progress() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE work_order_progress p
    SET
        good_quantity = p.good_quantity +
            GREATEST(NEW.good_parts - p.last_machine_good, 0),
        rejected_quantity = p.rejected_quantity +
            GREATEST(NEW.rejected - p.last_machine_rejected, 0),
        last_machine_good = NEW.good_parts,
        last_machine_rejected = NEW.rejected,
        last_sample_time = NEW.sample_time,
        updated_at = NOW()
    FROM machine_active_order a
    JOIN work_orders w
      ON w.work_order_id = a.work_order_id
    WHERE a.machine_id = NEW.machine_id
      AND p.work_order_id = a.work_order_id
      AND w.machine_id = NEW.machine_id
      AND w.status = 'IN_PROGRESS'
      AND NEW.sample_time > p.last_sample_time;

    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: erp_production_baselines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.erp_production_baselines (
    work_order_id character varying(50) NOT NULL,
    mes_good_baseline integer NOT NULL,
    erp_manufactured_baseline integer NOT NULL,
    captured_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: erp_production_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.erp_production_batches (
    batch_id character varying(100) NOT NULL,
    work_order_id character varying(50) NOT NULL,
    quantity integer NOT NULL,
    mes_good_start integer NOT NULL,
    mes_good_end integer NOT NULL,
    status character varying(30) DEFAULT 'PENDING'::character varying NOT NULL,
    erp_stock_entry character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    posted_at timestamp with time zone,
    CONSTRAINT erp_production_batches_check CHECK (((mes_good_end - mes_good_start) = quantity)),
    CONSTRAINT erp_production_batches_quantity_check CHECK ((quantity > 0))
);


--
-- Name: machine_active_order; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.machine_active_order (
    machine_id character varying(50) NOT NULL,
    work_order_id character varying(50) NOT NULL
);


--
-- Name: machine_samples; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.machine_samples (
    id bigint NOT NULL,
    machine_id character varying(50) NOT NULL,
    sample_time timestamp with time zone NOT NULL,
    machine_status character varying(30),
    produced integer,
    good_parts integer,
    rejected integer,
    temperature_c numeric(8,2),
    cycle_time_s numeric(8,2),
    vibration_mm_s numeric(8,2),
    source_protocol character varying(30)
);


--
-- Name: machine_samples_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.machine_samples_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: machine_samples_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.machine_samples_id_seq OWNED BY public.machine_samples.id;


--
-- Name: mes_unit_serials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mes_unit_serials (
    serial_number text NOT NULL,
    batch_id text NOT NULL,
    work_order_id text NOT NULL,
    erp_stock_entry text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: work_order_progress; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.work_order_progress (
    work_order_id character varying(50) NOT NULL,
    good_quantity integer DEFAULT 0 NOT NULL,
    rejected_quantity integer DEFAULT 0 NOT NULL,
    last_machine_good integer NOT NULL,
    last_machine_rejected integer NOT NULL,
    last_sample_time timestamp with time zone NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: work_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.work_orders (
    work_order_id character varying(50) NOT NULL,
    product character varying(100) NOT NULL,
    machine_id character varying(50) NOT NULL,
    target_quantity integer NOT NULL,
    status character varying(30) DEFAULT 'IN_PROGRESS'::character varying,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: machine_samples id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.machine_samples ALTER COLUMN id SET DEFAULT nextval('public.machine_samples_id_seq'::regclass);


--
-- Name: erp_production_baselines erp_production_baselines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.erp_production_baselines
    ADD CONSTRAINT erp_production_baselines_pkey PRIMARY KEY (work_order_id);


--
-- Name: erp_production_batches erp_production_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.erp_production_batches
    ADD CONSTRAINT erp_production_batches_pkey PRIMARY KEY (batch_id);


--
-- Name: erp_production_batches erp_production_batches_work_order_id_mes_good_start_mes_goo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.erp_production_batches
    ADD CONSTRAINT erp_production_batches_work_order_id_mes_good_start_mes_goo_key UNIQUE (work_order_id, mes_good_start, mes_good_end);


--
-- Name: machine_active_order machine_active_order_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.machine_active_order
    ADD CONSTRAINT machine_active_order_pkey PRIMARY KEY (machine_id);


--
-- Name: machine_samples machine_samples_machine_id_sample_time_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.machine_samples
    ADD CONSTRAINT machine_samples_machine_id_sample_time_key UNIQUE (machine_id, sample_time);


--
-- Name: machine_samples machine_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.machine_samples
    ADD CONSTRAINT machine_samples_pkey PRIMARY KEY (id);


--
-- Name: mes_unit_serials mes_unit_serials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mes_unit_serials
    ADD CONSTRAINT mes_unit_serials_pkey PRIMARY KEY (serial_number);


--
-- Name: work_order_progress work_order_progress_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_order_progress
    ADD CONSTRAINT work_order_progress_pkey PRIMARY KEY (work_order_id);


--
-- Name: work_orders work_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_orders
    ADD CONSTRAINT work_orders_pkey PRIMARY KEY (work_order_id);


--
-- Name: erp_production_batches_stock_entry_uidx; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX erp_production_batches_stock_entry_uidx ON public.erp_production_batches USING btree (erp_stock_entry) WHERE (erp_stock_entry IS NOT NULL);


--
-- Name: machine_samples mes_progress_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER mes_progress_trigger AFTER INSERT ON public.machine_samples FOR EACH ROW EXECUTE FUNCTION public.record_mes_progress();


--
-- Name: erp_production_baselines erp_production_baselines_work_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.erp_production_baselines
    ADD CONSTRAINT erp_production_baselines_work_order_id_fkey FOREIGN KEY (work_order_id) REFERENCES public.work_orders(work_order_id);


--
-- Name: erp_production_batches erp_production_batches_work_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.erp_production_batches
    ADD CONSTRAINT erp_production_batches_work_order_id_fkey FOREIGN KEY (work_order_id) REFERENCES public.work_orders(work_order_id);


--
-- Name: machine_active_order machine_active_order_work_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.machine_active_order
    ADD CONSTRAINT machine_active_order_work_order_id_fkey FOREIGN KEY (work_order_id) REFERENCES public.work_orders(work_order_id);


--
-- Name: work_order_progress work_order_progress_work_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_order_progress
    ADD CONSTRAINT work_order_progress_work_order_id_fkey FOREIGN KEY (work_order_id) REFERENCES public.work_orders(work_order_id);


--
-- PostgreSQL database dump complete
--

\unrestrict LpxFwdW5QSaiIVt7IOYUQzuK9i4tABzA0hF2nd6Gn1F2GgccKwmxbkcbNRJSExj
