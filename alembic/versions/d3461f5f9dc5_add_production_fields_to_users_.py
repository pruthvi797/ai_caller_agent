"""add_production_fields_to_users_dealerships_cars

Revision ID: d3461f5f9dc5
Revises: 
Create Date: 2026-03-05 11:53:03.740850

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd3461f5f9dc5'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop old tables only if they exist (safe for fresh DBs)
    op.execute("DROP TABLE IF EXISTS leads CASCADE")
    op.execute("DROP TABLE IF EXISTS calls CASCADE")
    op.execute("DROP TABLE IF EXISTS campaign_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_config CASCADE")
    op.execute("DROP TABLE IF EXISTS document_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS campaigns CASCADE")
    op.add_column('car_models', sa.Column('brand', sa.String(length=100), nullable=False))
    op.add_column('car_models', sa.Column('model_year', sa.Integer(), nullable=False))
    op.add_column('car_models', sa.Column('sku_code', sa.String(length=50), nullable=True))
    op.add_column('car_models', sa.Column('transmission', sa.String(length=30), nullable=False))
    op.add_column('car_models', sa.Column('drive_type', sa.String(length=20), nullable=True))
    op.add_column('car_models', sa.Column('seating_capacity', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('available_colors', sa.Text(), nullable=True))
    op.add_column('car_models', sa.Column('price_ex_showroom', sa.DECIMAL(precision=12, scale=2), nullable=False))
    op.add_column('car_models', sa.Column('price_on_road', sa.DECIMAL(precision=12, scale=2), nullable=True))
    op.add_column('car_models', sa.Column('emi_starting_from', sa.DECIMAL(precision=10, scale=2), nullable=True))
    op.add_column('car_models', sa.Column('engine_cc', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('engine_description', sa.String(length=150), nullable=True))
    op.add_column('car_models', sa.Column('max_power_bhp', sa.DECIMAL(precision=6, scale=2), nullable=True))
    op.add_column('car_models', sa.Column('max_torque_nm', sa.DECIMAL(precision=6, scale=2), nullable=True))
    op.add_column('car_models', sa.Column('mileage_kmpl', sa.DECIMAL(precision=5, scale=2), nullable=True))
    op.add_column('car_models', sa.Column('top_speed_kmph', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('boot_space_litres', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('ground_clearance_mm', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('kerb_weight_kg', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('length_mm', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('width_mm', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('height_mm', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('wheelbase_mm', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('fuel_tank_capacity_litres', sa.DECIMAL(precision=5, scale=1), nullable=True))
    op.add_column('car_models', sa.Column('ncap_rating', sa.String(length=10), nullable=True))
    op.add_column('car_models', sa.Column('airbags_count', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('has_abs', sa.Boolean(), nullable=True))
    op.add_column('car_models', sa.Column('has_esp', sa.Boolean(), nullable=True))
    op.add_column('car_models', sa.Column('key_features', sa.Text(), nullable=True))
    op.add_column('car_models', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('car_models', sa.Column('highlights', sa.Text(), nullable=True))
    op.add_column('car_models', sa.Column('thumbnail_image', sa.Text(), nullable=True))
    op.add_column('car_models', sa.Column('image_gallery', sa.Text(), nullable=True))
    op.add_column('car_models', sa.Column('current_offer', sa.Text(), nullable=True))
    op.add_column('car_models', sa.Column('offer_valid_until', sa.TIMESTAMP(), nullable=True))
    op.add_column('car_models', sa.Column('exchange_bonus', sa.DECIMAL(precision=10, scale=2), nullable=True))
    op.add_column('car_models', sa.Column('corporate_discount', sa.DECIMAL(precision=10, scale=2), nullable=True))
    op.add_column('car_models', sa.Column('stock_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('car_models', sa.Column('availability_status', sa.String(length=30), nullable=False, server_default='available'))
    op.add_column('car_models', sa.Column('delivery_weeks', sa.Integer(), nullable=True))
    op.add_column('car_models', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('car_models', sa.Column('is_featured', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('car_models', sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True))
    op.alter_column('car_models', 'dealership_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.alter_column('car_models', 'model_name',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('car_models', 'variant',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('car_models', 'category',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('car_models', 'fuel_type',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('car_models', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('car_models', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.create_index(op.f('ix_car_models_dealership_id'), 'car_models', ['dealership_id'], unique=False)
    op.create_unique_constraint('uq_car_models_sku_code', 'car_models', ['sku_code'])
    op.drop_column('car_models', 'features')
    op.add_column('dealerships', sa.Column('brand', sa.String(length=100), nullable=False, server_default='Suzuki'))
    op.add_column('dealerships', sa.Column('registration_number', sa.String(length=100), nullable=True))
    op.add_column('dealerships', sa.Column('gst_number', sa.String(length=50), nullable=True))
    op.add_column('dealerships', sa.Column('city', sa.String(length=100), nullable=False, server_default='Unknown'))
    op.add_column('dealerships', sa.Column('state', sa.String(length=100), nullable=False, server_default='Unknown'))
    op.add_column('dealerships', sa.Column('country', sa.String(length=100), nullable=False, server_default='India'))
    op.add_column('dealerships', sa.Column('pincode', sa.String(length=20), nullable=True))
    op.add_column('dealerships', sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True))
    op.add_column('dealerships', sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True))
    op.add_column('dealerships', sa.Column('alternate_phone', sa.String(length=20), nullable=True))
    op.add_column('dealerships', sa.Column('contact_email', sa.String(length=255), nullable=True))
    op.add_column('dealerships', sa.Column('website_url', sa.String(length=500), nullable=True))
    op.add_column('dealerships', sa.Column('banner_image', sa.Text(), nullable=True))
    op.add_column('dealerships', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('dealerships', sa.Column('established_year', sa.String(length=4), nullable=True))
    op.add_column('dealerships', sa.Column('total_employees', sa.String(length=10), nullable=True))
    op.add_column('dealerships', sa.Column('monthly_target_calls', sa.String(length=10), nullable=True))
    op.add_column('dealerships', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('dealerships', sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True))
    op.alter_column('dealerships', 'user_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.alter_column('dealerships', 'name',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('dealerships', 'location',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('dealerships', 'showroom_address',
               existing_type=sa.VARCHAR(),
               type_=sa.Text(),
               nullable=False)
    op.alter_column('dealerships', 'contact_phone',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('dealerships', 'logo',
               existing_type=sa.VARCHAR(),
               type_=sa.Text(),
               existing_nullable=True)
    op.alter_column('dealerships', 'status',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('dealerships', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('dealerships', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.create_unique_constraint('uq_dealerships_gst_number', 'dealerships', ['gst_number'])
    op.create_unique_constraint('uq_dealerships_registration_number', 'dealerships', ['registration_number'])
    op.add_column('users', sa.Column('first_name', sa.String(length=100), nullable=False, server_default='Unknown'))
    op.add_column('users', sa.Column('last_name', sa.String(length=100), nullable=False, server_default='Unknown'))
    op.add_column('users', sa.Column('profile_picture', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('designation', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('department', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('last_login_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('users', sa.Column('password_changed_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('locked_until', sa.TIMESTAMP(), nullable=True))
    op.add_column('users', sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True))
    op.alter_column('users', 'email',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('users', 'password_hash',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('users', 'phone',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('users', 'employee_id',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('users', 'company_name',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('users', 'role',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.alter_column('users', 'permissions',
               existing_type=sa.VARCHAR(),
               type_=sa.Text(),
               existing_nullable=True)
    op.alter_column('users', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('users', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.drop_constraint('users_email_key', 'users', type_='unique')
    op.drop_constraint('users_employee_id_key', 'users', type_='unique')
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_employee_id'), 'users', ['employee_id'], unique=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_users_employee_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.create_unique_constraint('users_employee_id_key', 'users', ['employee_id'])
    op.create_unique_constraint('users_email_key', 'users', ['email'])
    op.alter_column('users', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('users', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('users', 'permissions',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(),
               existing_nullable=True)
    op.alter_column('users', 'role',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('users', 'company_name',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('users', 'employee_id',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('users', 'phone',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('users', 'password_hash',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('users', 'email',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.drop_column('users', 'deleted_at')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'is_verified')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'bio')
    op.drop_column('users', 'department')
    op.drop_column('users', 'designation')
    op.drop_column('users', 'profile_picture')
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')
    op.drop_constraint('uq_dealerships_gst_number', 'dealerships', type_='unique')
    op.drop_constraint('uq_dealerships_registration_number', 'dealerships', type_='unique')
    op.alter_column('dealerships', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('dealerships', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('dealerships', 'status',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('dealerships', 'logo',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(),
               existing_nullable=True)
    op.alter_column('dealerships', 'contact_phone',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('dealerships', 'showroom_address',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(),
               nullable=True)
    op.alter_column('dealerships', 'location',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('dealerships', 'name',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('dealerships', 'user_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.drop_column('dealerships', 'deleted_at')
    op.drop_column('dealerships', 'is_verified')
    op.drop_column('dealerships', 'monthly_target_calls')
    op.drop_column('dealerships', 'total_employees')
    op.drop_column('dealerships', 'established_year')
    op.drop_column('dealerships', 'description')
    op.drop_column('dealerships', 'banner_image')
    op.drop_column('dealerships', 'website_url')
    op.drop_column('dealerships', 'contact_email')
    op.drop_column('dealerships', 'alternate_phone')
    op.drop_column('dealerships', 'longitude')
    op.drop_column('dealerships', 'latitude')
    op.drop_column('dealerships', 'pincode')
    op.drop_column('dealerships', 'country')
    op.drop_column('dealerships', 'state')
    op.drop_column('dealerships', 'city')
    op.drop_column('dealerships', 'gst_number')
    op.drop_column('dealerships', 'registration_number')
    op.drop_column('dealerships', 'brand')
    op.add_column('car_models', sa.Column('features', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.drop_constraint('uq_car_models_sku_code', 'car_models', type_='unique')
    op.drop_index(op.f('ix_car_models_dealership_id'), table_name='car_models')
    op.alter_column('car_models', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('car_models', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('car_models', 'fuel_type',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('car_models', 'category',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('car_models', 'variant',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('car_models', 'model_name',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.alter_column('car_models', 'dealership_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.drop_column('car_models', 'deleted_at')
    op.drop_column('car_models', 'is_featured')
    op.drop_column('car_models', 'is_active')
    op.drop_column('car_models', 'delivery_weeks')
    op.drop_column('car_models', 'availability_status')
    op.drop_column('car_models', 'stock_count')
    op.drop_column('car_models', 'corporate_discount')
    op.drop_column('car_models', 'exchange_bonus')
    op.drop_column('car_models', 'offer_valid_until')
    op.drop_column('car_models', 'current_offer')
    op.drop_column('car_models', 'image_gallery')
    op.drop_column('car_models', 'thumbnail_image')
    op.drop_column('car_models', 'highlights')
    op.drop_column('car_models', 'description')
    op.drop_column('car_models', 'key_features')
    op.drop_column('car_models', 'has_esp')
    op.drop_column('car_models', 'has_abs')
    op.drop_column('car_models', 'airbags_count')
    op.drop_column('car_models', 'ncap_rating')
    op.drop_column('car_models', 'fuel_tank_capacity_litres')
    op.drop_column('car_models', 'wheelbase_mm')
    op.drop_column('car_models', 'height_mm')
    op.drop_column('car_models', 'width_mm')
    op.drop_column('car_models', 'length_mm')
    op.drop_column('car_models', 'kerb_weight_kg')
    op.drop_column('car_models', 'ground_clearance_mm')
    op.drop_column('car_models', 'boot_space_litres')
    op.drop_column('car_models', 'top_speed_kmph')
    op.drop_column('car_models', 'mileage_kmpl')
    op.drop_column('car_models', 'max_torque_nm')
    op.drop_column('car_models', 'max_power_bhp')
    op.drop_column('car_models', 'engine_description')
    op.drop_column('car_models', 'engine_cc')
    op.drop_column('car_models', 'emi_starting_from')
    op.drop_column('car_models', 'price_on_road')
    op.drop_column('car_models', 'price_ex_showroom')
    op.drop_column('car_models', 'available_colors')
    op.drop_column('car_models', 'seating_capacity')
    op.drop_column('car_models', 'drive_type')
    op.drop_column('car_models', 'transmission')
    op.drop_column('car_models', 'sku_code')
    op.drop_column('car_models', 'model_year')
    op.drop_column('car_models', 'brand')
    op.create_table('document_chunks',
    sa.Column('chunk_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('document_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('chunk_text', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('embedding', sa.Text(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['documents.document_id'], name='document_chunks_document_id_fkey'),
    sa.PrimaryKeyConstraint('chunk_id', name='document_chunks_pkey')
    )
    op.create_table('agent_config',
    sa.Column('agent_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('campaign_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('voice', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('system_prompt', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('knowledge_base_id', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.campaign_id'], name='agent_config_campaign_id_fkey'),
    sa.PrimaryKeyConstraint('agent_id', name='agent_config_pkey')
    )
    op.create_table('campaign_documents',
    sa.Column('campaign_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('document_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.campaign_id'], name='campaign_documents_campaign_id_fkey'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.document_id'], name='campaign_documents_document_id_fkey'),
    sa.PrimaryKeyConstraint('campaign_id', 'document_id', name='campaign_documents_pkey')
    )
    op.create_table('calls',
    sa.Column('call_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('lead_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('campaign_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('call_status', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('call_duration', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('call_outcome', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('transcript', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('call_recording_url', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.campaign_id'], name='calls_campaign_id_fkey'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.lead_id'], name='calls_lead_id_fkey'),
    sa.PrimaryKeyConstraint('call_id', name='calls_pkey')
    )
    op.create_table('documents',
    sa.Column('document_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('car_model_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('file_name', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('file_type', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('file_path', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('processed_text', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('uploaded_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['car_model_id'], ['car_models.car_model_id'], name='documents_car_model_id_fkey'),
    sa.PrimaryKeyConstraint('document_id', name='documents_pkey')
    )
    op.create_table('campaigns',
    sa.Column('campaign_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('dealership_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('car_model_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('campaign_name', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('promotion_type', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('start_date', sa.DATE(), autoincrement=False, nullable=True),
    sa.Column('end_date', sa.DATE(), autoincrement=False, nullable=True),
    sa.Column('status', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['car_model_id'], ['car_models.car_model_id'], name='campaigns_car_model_id_fkey'),
    sa.ForeignKeyConstraint(['dealership_id'], ['dealerships.dealership_id'], name='campaigns_dealership_id_fkey'),
    sa.PrimaryKeyConstraint('campaign_id', name='campaigns_pkey')
    )
    op.create_table('leads',
    sa.Column('lead_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('campaign_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('phone', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('email', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('budget', sa.NUMERIC(), autoincrement=False, nullable=True),
    sa.Column('current_car', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('interest_level', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.campaign_id'], name='leads_campaign_id_fkey'),
    sa.PrimaryKeyConstraint('lead_id', name='leads_pkey')
    )
    # ### end Alembic commands ###