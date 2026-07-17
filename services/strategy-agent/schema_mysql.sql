create table marketing_plan (
  campaign_id varchar(32) primary key,
  product varchar(32) not null,
  audience_size int not null,
  predicted_uplift decimal(8, 2) not null,
  predicted_roi decimal(8, 2) not null,
  payload json not null,
  created_at timestamp default current_timestamp,
  updated_at timestamp default current_timestamp on update current_timestamp
);

create table marketing_experiment_result (
  id bigint primary key auto_increment,
  campaign_id varchar(32) not null,
  group_name varchar(32) not null,
  exposure_count int not null,
  click_count int not null,
  conversion_count int not null,
  complaint_count int not null,
  cost_amount decimal(14, 2) not null,
  revenue_amount decimal(14, 2) not null,
  created_at timestamp default current_timestamp,
  index idx_campaign_id (campaign_id)
);

create table marketing_knowledge_doc (
  id bigint primary key auto_increment,
  doc_type varchar(64) not null,
  title varchar(255) not null,
  content text not null,
  embedding_id varchar(128),
  created_at timestamp default current_timestamp
);
