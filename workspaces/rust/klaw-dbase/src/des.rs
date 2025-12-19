//! Optimal dBase Deserialization Implementation
//!
//! This module provides high-performance deserialization for converting dBase
//! field values to Polars arrays. It follows the same architectural patterns
//! as the Avro deserializer while being optimized for the simpler dBase format.
//!
//! The module handles:
//! - Schema conversion from dBase field definitions to Polars schema
//! - Value building from dBase FieldValue types to Polars arrays
//! - Type mapping between dBase and Polars data types
//!
//! Note: This module does NOT handle file I/O or record parsing. Those concerns
//! are handled by the dbase crate's Reader and FieldIterator types.

use std::any::Any;
use std::collections::BTreeMap;

use dbase::{FieldType, FieldValue};
use polars::error::{PolarsError, PolarsResult};
use polars::prelude::{
    ArrowDataType, CompatLevel, DataType, Field, PlSmallStr, Schema as PlSchema, TimeUnit, TimeZone,
};
use polars_arrow::array::{
    Array, MutableArray, MutableBinaryViewArray, MutableBooleanArray, MutableListArray,
    MutableNullArray, MutablePrimitiveArray, StructArray, TryExtend,
};
use polars_arrow::bitmap::MutableBitmap;

// Re-export the error from our error module
pub use super::error::Error as ValueError;

impl From<ValueError> for PolarsError {
    fn from(err: ValueError) -> Self {
        PolarsError::SchemaMismatch(err.to_string().into())
    }
}

// ============================================================================
// Schema Conversion (following Avro's try_from_schema pattern)
// ============================================================================

/// Convert dBase field definitions to Polars schema
///
/// This function mirrors the Avro implementation's try_from_schema function.
/// It converts dBase field metadata into a Polars schema.
pub fn try_from_schema(
    field_definitions: &[dbase::FieldInfo],
    single_column_name: Option<&PlSmallStr>,
) -> Result<PlSchema, ValueError> {
    if field_definitions.is_empty() {
        return Err(ValueError::InternalError {
            message: "dBase table has no fields".to_string(),
        });
    }

    let fields = convert_dbase_fields_to_polars(field_definitions)?;

    // Handle single_col_name as column selection and rename
    if let Some(col_name) = single_column_name {
        // If there's only one field, rename it to the specified name
        if fields.len() == 1 {
            return Ok(PlSchema::from_iter([(
                col_name.clone(),
                fields[0].dtype.clone(),
            )]));
        } else {
            // If there are multiple fields, look for a field matching the column name
            // This allows single_col_name to work as both selection and rename
            for field in &fields {
                if field.name.as_str() == col_name.as_str() {
                    // Found matching field, return schema with just this field
                    return Ok(PlSchema::from_iter([(
                        col_name.clone(),
                        field.dtype.clone(),
                    )]));
                }
            }
            // If no matching field found, fall back to original behavior
            // This maintains backward compatibility
        }
    }

    Ok(PlSchema::from_iter(fields))
}

/// Convert dBase field definitions to Polars fields
fn convert_dbase_fields_to_polars(
    field_definitions: &[dbase::FieldInfo],
) -> Result<Vec<Field>, ValueError> {
    let mut parser = DataTypeParser::default();
    parser.convert_field_definitions(field_definitions)
}

/// Parser for converting dBase field types to Polars DataTypes
///
/// This mirrors the Avro implementation's DataTypeParser struct.
#[derive(Debug, Default)]
struct DataTypeParser {
    /// Cache for already converted types to avoid duplicates
    type_cache: BTreeMap<String, DataType>,
}

impl DataTypeParser {
    /// Convert a collection of dBase field definitions to Polars fields
    fn convert_field_definitions(
        &mut self,
        field_definitions: &[dbase::FieldInfo],
    ) -> Result<Vec<Field>, ValueError> {
        field_definitions
            .iter()
            .map(|field_info| {
                let field_name = self.sanitize_field_name(field_info.name());
                let dtype = self.convert_field_type(&field_info.field_type())?;
                Ok(Field {
                    name: field_name.into(),
                    dtype,
                })
            })
            .collect::<Result<Vec<_>, ValueError>>()
    }

    /// Sanitize field names to remove null bytes and other invalid characters
    ///
    /// DBC files can have field names with null bytes or other problematic characters
    /// that cause issues in Arrow FFI. This function cleans them up.
    fn sanitize_field_name(&self, name: &str) -> String {
        // Remove null bytes and any characters after the first null byte
        let cleaned = if let Some(null_pos) = name.find('\0') {
            &name[..null_pos]
        } else {
            name
        };

        // Trim whitespace and replace any remaining problematic characters
        let mut result = cleaned.trim().to_string();

        // Replace empty field names with a default
        if result.is_empty() {
            result = "unnamed_field".to_string();
        }

        // Ensure the name is valid for Arrow (no control characters, etc.)
        result.retain(|c| c.is_ascii_graphic() || c == '_' || c == ' ');

        // If the result is empty after cleaning, use a default name
        if result.is_empty() {
            result = "unnamed_field".to_string();
        }

        result
    }

    /// Convert a single dBase field type to Polars DataType
    fn convert_field_type(&mut self, field_type: &FieldType) -> Result<DataType, ValueError> {
        // Use string representation for cache since FieldType doesn't implement Hash
        let type_key = format!("{:?}", field_type);
        if let Some(cached) = self.type_cache.get(&type_key) {
            return Ok(cached.clone());
        }

        let dtype = match field_type {
            FieldType::Character => DataType::String,
            FieldType::Logical => DataType::Boolean,
            FieldType::Integer => DataType::Int32,
            FieldType::Date => DataType::Date,
            FieldType::DateTime => DataType::Datetime(TimeUnit::Milliseconds, Some(TimeZone::UTC)),
            FieldType::Float => DataType::Float32,
            FieldType::Numeric | FieldType::Currency | FieldType::Double => DataType::Float64,
            FieldType::Memo => DataType::String,
        };

        // Cache the result
        self.type_cache.insert(type_key, dtype.clone());
        Ok(dtype)
    }
}

// ============================================================================
// Value Builder Trait (following Avro's ValueBuilder pattern)
// ============================================================================

/// Core trait for building Polars arrays from dBase field values
///
/// This mirrors the Avro implementation's ValueBuilder trait.
pub trait ValueBuilder: MutableArray {
    /// Push a dBase field value into the array
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()>;
}

impl MutableArray for Box<dyn ValueBuilder> {
    fn dtype(&self) -> &ArrowDataType {
        self.as_ref().dtype()
    }

    fn len(&self) -> usize {
        self.as_ref().len()
    }

    fn validity(&self) -> Option<&MutableBitmap> {
        self.as_ref().validity()
    }

    fn as_box(&mut self) -> Box<dyn Array> {
        self.as_mut().as_box()
    }

    fn as_any(&self) -> &dyn Any {
        self.as_ref().as_any()
    }

    fn as_mut_any(&mut self) -> &mut dyn Any {
        self.as_mut().as_mut_any()
    }

    fn push_null(&mut self) {
        self.as_mut().push_null();
    }

    fn reserve(&mut self, additional: usize) {
        self.as_mut().reserve(additional);
    }

    fn shrink_to_fit(&mut self) {
        self.as_mut().shrink_to_fit();
    }
}

impl ValueBuilder for Box<dyn ValueBuilder> {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        self.as_mut().try_push_value(value)
    }
}

// ============================================================================
// Value Builder Implementations (following Avro's pattern)
// ============================================================================

impl ValueBuilder for MutableNullArray {
    fn try_push_value(&mut self, _value: &FieldValue) -> PolarsResult<()> {
        self.push_null();
        Ok(())
    }
}

impl ValueBuilder for MutableBooleanArray {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        match value {
            FieldValue::Logical(Some(b)) => self.push_value(*b),
            FieldValue::Logical(None) => self.push_null(),
            _ => {
                return Err(PolarsError::SchemaMismatch(
                    format!("expected bool but got {:?}", value.field_type()).into(),
                ));
            }
        }
        Ok(())
    }
}

impl ValueBuilder for MutableBinaryViewArray<str> {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        match value {
            FieldValue::Character(Some(s)) => self.push_value(s),
            FieldValue::Character(None) => self.push_null(),
            FieldValue::Memo(s) => self.push_value(s),
            _ => {
                return Err(PolarsError::SchemaMismatch(
                    format!("expected string but got {:?}", value.field_type()).into(),
                ));
            }
        }
        Ok(())
    }
}

impl ValueBuilder for MutableBinaryViewArray<[u8]> {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        match value {
            FieldValue::Character(Some(s)) => self.push_value(s.as_bytes()),
            FieldValue::Character(None) => self.push_null(),
            FieldValue::Memo(s) => self.push_value(s.as_bytes()),
            _ => {
                return Err(PolarsError::SchemaMismatch(
                    format!("expected bytes but got {:?}", value.field_type()).into(),
                ));
            }
        }
        Ok(())
    }
}

impl ValueBuilder for MutablePrimitiveArray<i32> {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        match value {
            FieldValue::Integer(i) => self.push_value(*i),
            FieldValue::Date(Some(d)) => self.push_value(d.to_unix_days()),
            FieldValue::Date(None) => self.push_null(),
            _ => {
                return Err(PolarsError::SchemaMismatch(
                    format!("expected int but got {:?}", value.field_type()).into(),
                ));
            }
        }
        Ok(())
    }
}

impl ValueBuilder for MutablePrimitiveArray<i64> {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        match value {
            FieldValue::DateTime(dt) => self.push_value(dt.to_unix_timestamp()),
            _ => {
                return Err(PolarsError::SchemaMismatch(
                    format!(
                        "expected long, timestamp, or time but got {:?}",
                        value.field_type()
                    )
                    .into(),
                ));
            }
        }
        Ok(())
    }
}

impl ValueBuilder for MutablePrimitiveArray<f32> {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        match value {
            FieldValue::Float(Some(f)) => self.push_value(*f),
            FieldValue::Float(None) => self.push_null(),
            _ => {
                return Err(PolarsError::SchemaMismatch(
                    format!("expected float but got {:?}", value.field_type()).into(),
                ));
            }
        }
        Ok(())
    }
}

impl ValueBuilder for MutablePrimitiveArray<f64> {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        match value {
            FieldValue::Numeric(Some(n)) => self.push_value(*n),
            FieldValue::Numeric(None) => self.push_null(),
            FieldValue::Currency(c) => self.push_value(*c),
            FieldValue::Double(d) => self.push_value(*d),
            _ => {
                return Err(PolarsError::SchemaMismatch(
                    format!("expected double but got {:?}", value.field_type()).into(),
                ));
            }
        }
        Ok(())
    }
}

// ============================================================================
// Builder Factory (following Avro's new_value_builder pattern)
// ============================================================================

/// Create a new value builder for the given data type
///
/// This mirrors the Avro implementation's new_value_builder function.
pub fn new_value_builder(dtype: &DataType, capacity: usize) -> Box<dyn ValueBuilder> {
    match dtype {
        DataType::Boolean => Box::new(MutableBooleanArray::with_capacity(capacity)),
        DataType::Null => Box::new(MutableNullArray::new(ArrowDataType::Null, 0)),
        DataType::Int32 => Box::new(MutablePrimitiveArray::<i32>::with_capacity(capacity)),
        DataType::Date => Box::new(
            MutablePrimitiveArray::<i32>::try_new(
                ArrowDataType::Date32,
                Vec::with_capacity(capacity),
                None,
            )
            .unwrap(),
        ),
        DataType::Int64 => Box::new(MutablePrimitiveArray::<i64>::with_capacity(capacity)),
        DataType::Datetime(_, _) | DataType::Time => Box::new(
            MutablePrimitiveArray::<i64>::try_new(
                dtype.to_arrow(CompatLevel::newest()),
                Vec::with_capacity(capacity),
                None,
            )
            .unwrap(),
        ),
        DataType::Float32 => Box::new(MutablePrimitiveArray::<f32>::with_capacity(capacity)),
        DataType::Float64 => Box::new(MutablePrimitiveArray::<f64>::with_capacity(capacity)),
        DataType::String => Box::new(MutableBinaryViewArray::<str>::with_capacity(capacity)),
        DataType::Binary => Box::new(MutableBinaryViewArray::<[u8]>::with_capacity(capacity)),
        DataType::List(dtype) => Box::new(ListBuilder::with_capacity(dtype, capacity)),
        DataType::Struct(fields) => Box::new(StructBuilder::with_capacity(fields, capacity)),
        // Skip enum/categorical support for now as it's complex and not needed for dBase
        _ => Box::new(MutableNullArray::new(ArrowDataType::Null, 0)),
    }
}

// ============================================================================
// Complex Type Builders (following Avro's pattern)
// ============================================================================

#[derive(Debug)]
pub struct ListBuilder {
    inner: MutableListArray<i64, Box<dyn ValueBuilder>>,
}

impl ListBuilder {
    pub fn with_capacity(dtype: &DataType, capacity: usize) -> Self {
        Self {
            inner: MutableListArray::new_from(
                new_value_builder(dtype, capacity),
                ArrowDataType::LargeList(Box::new(
                    dtype.to_arrow_field("item".into(), CompatLevel::newest()),
                )),
                capacity,
            ),
        }
    }
}

impl<'a> TryExtend<Option<&'a FieldValue>> for Box<dyn ValueBuilder> {
    fn try_extend<I: IntoIterator<Item = Option<&'a FieldValue>>>(
        &mut self,
        iter: I,
    ) -> PolarsResult<()> {
        for item in iter {
            self.try_push_value(item.unwrap())?;
        }
        Ok(())
    }
}

impl MutableArray for ListBuilder {
    fn dtype(&self) -> &ArrowDataType {
        self.inner.dtype()
    }

    fn len(&self) -> usize {
        self.inner.len()
    }

    fn validity(&self) -> Option<&MutableBitmap> {
        self.inner.validity()
    }

    fn as_box(&mut self) -> Box<dyn Array> {
        self.inner.as_box()
    }

    fn as_any(&self) -> &dyn Any {
        self
    }

    fn as_mut_any(&mut self) -> &mut dyn Any {
        self
    }

    fn push_null(&mut self) {
        self.inner.push_null();
    }

    fn reserve(&mut self, additional: usize) {
        self.inner.reserve(additional);
    }

    fn shrink_to_fit(&mut self) {
        self.inner.shrink_to_fit();
    }
}

impl ValueBuilder for ListBuilder {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        // dBase doesn't have array types, so this would be for future extensions
        Err(PolarsError::SchemaMismatch(
            format!("expected array but got {:?}", value.field_type()).into(),
        ))
    }
}

#[derive(Debug)]
pub struct StructBuilder {
    dtype: ArrowDataType,
    len: usize,
    values: Vec<Box<dyn ValueBuilder>>,
    validity: Option<MutableBitmap>,
}

impl StructBuilder {
    pub fn with_capacity(fields: &[Field], capacity: usize) -> Self {
        let values = fields
            .iter()
            .map(|field| new_value_builder(&field.dtype, capacity))
            .collect();
        Self {
            dtype: ArrowDataType::Struct(
                fields
                    .iter()
                    .map(|field| {
                        field
                            .dtype
                            .to_arrow_field(field.name.clone(), CompatLevel::newest())
                    })
                    .collect(),
            ),
            len: 0,
            values,
            validity: None,
        }
    }
}

impl MutableArray for StructBuilder {
    fn dtype(&self) -> &ArrowDataType {
        &self.dtype
    }

    fn len(&self) -> usize {
        self.len
    }

    fn validity(&self) -> Option<&MutableBitmap> {
        self.validity.as_ref()
    }

    fn as_box(&mut self) -> Box<dyn Array> {
        Box::new(StructArray::new(
            self.dtype.clone(),
            self.len,
            self.values.iter_mut().map(MutableArray::as_box).collect(),
            self.validity.as_ref().map(|bmp| bmp.clone().freeze()),
        ))
    }

    fn as_any(&self) -> &dyn Any {
        self
    }

    fn as_mut_any(&mut self) -> &mut dyn Any {
        self
    }

    fn push_null(&mut self) {
        match &mut self.validity {
            Some(val) => {
                val.push(false);
            }
            empty @ None => {
                let mut val = MutableBitmap::from_len_set(self.len);
                val.push(false);
                *empty = Some(val);
            }
        }
        for val in &mut self.values {
            val.push_null();
        }
        self.len += 1;
    }

    fn reserve(&mut self, additional: usize) {
        if let Some(val) = &mut self.validity {
            val.reserve(additional);
        }
        for val in &mut self.values {
            val.reserve(additional);
        }
    }

    fn shrink_to_fit(&mut self) {
        if let Some(val) = &mut self.validity {
            val.shrink_to_fit();
        }
        for val in &mut self.values {
            val.shrink_to_fit();
        }
    }
}

impl ValueBuilder for StructBuilder {
    fn try_push_value(&mut self, value: &FieldValue) -> PolarsResult<()> {
        // dBase doesn't have struct types, so this would be for future extensions
        Err(PolarsError::SchemaMismatch(
            format!("expected record but got {:?}", value.field_type()).into(),
        ))
    }
}

// ============================================================================
// Utility Functions
// ============================================================================

/// Convert dBase FieldType to Polars DataType (standalone function)
pub fn dbase_field_type_to_polars(field_type: &FieldType) -> Result<DataType, ValueError> {
    let mut parser = DataTypeParser::default();
    parser.convert_field_type(field_type)
}

/// Extension trait for FieldValue to get its type
pub trait FieldValueExt {
    fn field_type(&self) -> FieldType;
}

impl FieldValueExt for FieldValue {
    fn field_type(&self) -> FieldType {
        match self {
            FieldValue::Character(_) => FieldType::Character,
            FieldValue::Date(_) => FieldType::Date,
            FieldValue::Float(_) => FieldType::Float,
            FieldValue::Numeric(_) => FieldType::Numeric,
            FieldValue::Logical(_) => FieldType::Logical,
            FieldValue::Currency(_) => FieldType::Currency,
            FieldValue::DateTime(_) => FieldType::DateTime,
            FieldValue::Integer(_) => FieldType::Integer,
            FieldValue::Double(_) => FieldType::Double,
            FieldValue::Memo(_) => FieldType::Memo,
        }
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper function to create test field info using the public API
    fn create_test_field_info(name: &str, field_type: dbase::FieldType) -> MockFieldInfo {
        // For testing purposes, we'll create a mock that implements the same interface
        // Since we can't directly access the private fields_info, we'll create a mock
        create_mock_field_info(name, field_type)
    }

    /// Create a mock field info that implements the same interface as the real one
    fn create_mock_field_info(name: &str, field_type: dbase::FieldType) -> MockFieldInfo {
        MockFieldInfo {
            name: name.to_string(),
            field_type,
        }
    }

    /// Mock FieldInfo that implements the interface we need for testing
    #[derive(Debug, Clone)]
    struct MockFieldInfo {
        name: String,
        field_type: dbase::FieldType,
    }

    impl MockFieldInfo {
        pub fn name(&self) -> &str {
            &self.name
        }

        pub fn field_type(&self) -> dbase::FieldType {
            self.field_type
        }
    }

    /// Update the try_from_schema function to work with our mock for testing
    fn try_from_schema_with_mock(
        field_definitions: &[MockFieldInfo],
        single_column_name: Option<&PlSmallStr>,
    ) -> Result<PlSchema, ValueError> {
        if field_definitions.is_empty() {
            return Err(ValueError::InternalError {
                message: "dBase table has no fields".to_string(),
            });
        }

        let fields = convert_mock_fields_to_polars(field_definitions)?;

        if fields.len() == 1
            && let Some(col_name) = single_column_name
        {
            return Ok(PlSchema::from_iter([(
                col_name.clone(),
                fields[0].dtype.clone(),
            )]));
        }

        Ok(PlSchema::from_iter(fields))
    }

    fn convert_mock_fields_to_polars(
        field_definitions: &[MockFieldInfo],
    ) -> Result<Vec<Field>, ValueError> {
        let mut parser = DataTypeParser::default();
        field_definitions
            .iter()
            .map(|field_info| {
                let field_name = parser.sanitize_field_name(field_info.name());
                let dtype = parser.convert_field_type(&field_info.field_type())?;
                Ok(Field {
                    name: field_name.into(),
                    dtype,
                })
            })
            .collect::<Result<Vec<_>, ValueError>>()
    }

    #[test]
    fn test_empty_schema_error() {
        let result = try_from_schema(&[], None);
        assert!(result.is_err());
        match result.unwrap_err() {
            ValueError::InternalError { message, .. } => {
                assert_eq!(message, "dBase table has no fields");
            }
            _ => panic!("Expected InternalError"),
        }
    }

    #[test]
    fn test_schema_conversion_multiple_fields() {
        let fields = vec![
            create_test_field_info("ID", dbase::FieldType::Integer),
            create_test_field_info("NAME", dbase::FieldType::Character),
            create_test_field_info("ACTIVE", dbase::FieldType::Logical),
            create_test_field_info("SALARY", dbase::FieldType::Numeric),
            create_test_field_info("BIRTH_DATE", dbase::FieldType::Date),
        ];

        let schema = try_from_schema_with_mock(&fields, None).unwrap();
        assert_eq!(schema.len(), 5);

        // Check ID field
        let id_field = schema.get_at_index(0).unwrap();
        assert_eq!(id_field.0, "ID");
        assert!(matches!(id_field.1, DataType::Int32));

        // Check NAME field
        let name_field = schema.get_at_index(1).unwrap();
        assert_eq!(name_field.0, "NAME");
        assert!(matches!(name_field.1, DataType::String));

        // Check ACTIVE field
        let active_field = schema.get_at_index(2).unwrap();
        assert_eq!(active_field.0, "ACTIVE");
        assert!(matches!(active_field.1, DataType::Boolean));

        // Check SALARY field
        let salary_field = schema.get_at_index(3).unwrap();
        assert_eq!(salary_field.0, "SALARY");
        assert!(matches!(salary_field.1, DataType::Float64));

        // Check BIRTH_DATE field
        let birth_date_field = schema.get_at_index(4).unwrap();
        assert_eq!(birth_date_field.0, "BIRTH_DATE");
        assert!(matches!(birth_date_field.1, DataType::Date));
    }

    #[test]
    fn test_single_column_schema_with_rename() {
        let fields = vec![create_test_field_info("ID", dbase::FieldType::Integer)];
        let col_name = PlSmallStr::from("MY_ID");

        let schema = try_from_schema_with_mock(&fields, Some(&col_name)).unwrap();
        assert_eq!(schema.len(), 1);

        let field = schema.get_at_index(0).unwrap();
        assert_eq!(field.0, "MY_ID");
        assert!(matches!(field.1, DataType::Int32));
    }

    #[test]
    fn test_single_column_schema_no_rename() {
        let fields = vec![create_test_field_info("NAME", dbase::FieldType::Character)];

        let schema = try_from_schema_with_mock(&fields, None).unwrap();
        assert_eq!(schema.len(), 1);

        let field = schema.get_at_index(0).unwrap();
        assert_eq!(field.0, "NAME");
        assert!(matches!(field.1, DataType::String));
    }

    #[test]
    fn test_all_field_types_conversion() {
        let fields = vec![
            create_test_field_info("CHAR_FIELD", dbase::FieldType::Character),
            create_test_field_info("LOGICAL_FIELD", dbase::FieldType::Logical),
            create_test_field_info("INTEGER_FIELD", dbase::FieldType::Integer),
            create_test_field_info("DATE_FIELD", dbase::FieldType::Date),
            create_test_field_info("DATETIME_FIELD", dbase::FieldType::DateTime),
            create_test_field_info("FLOAT_FIELD", dbase::FieldType::Float),
            create_test_field_info("NUMERIC_FIELD", dbase::FieldType::Numeric),
            create_test_field_info("CURRENCY_FIELD", dbase::FieldType::Currency),
            create_test_field_info("DOUBLE_FIELD", dbase::FieldType::Double),
            create_test_field_info("MEMO_FIELD", dbase::FieldType::Memo),
        ];

        let schema = try_from_schema_with_mock(&fields, None).unwrap();
        assert_eq!(schema.len(), 10);

        let expected_types = vec![
            ("CHAR_FIELD", DataType::String),
            ("LOGICAL_FIELD", DataType::Boolean),
            ("INTEGER_FIELD", DataType::Int32),
            ("DATE_FIELD", DataType::Date),
            (
                "DATETIME_FIELD",
                DataType::Datetime(TimeUnit::Milliseconds, Some(TimeZone::UTC)),
            ),
            ("FLOAT_FIELD", DataType::Float32),
            ("NUMERIC_FIELD", DataType::Float64),
            ("CURRENCY_FIELD", DataType::Float64),
            ("DOUBLE_FIELD", DataType::Float64),
            ("MEMO_FIELD", DataType::String),
        ];

        for (i, (expected_name, expected_type)) in expected_types.into_iter().enumerate() {
            let field = schema.get_at_index(i).unwrap();
            assert_eq!(field.0, expected_name);
            assert_eq!(
                field.1, &expected_type,
                "Field {} expected type {:?}, got {:?}",
                expected_name, expected_type, field.1
            );
        }
    }

    #[test]
    fn test_schema_field_order_preservation() {
        let fields = vec![
            create_test_field_info("Z_FIELD", dbase::FieldType::Character),
            create_test_field_info("A_FIELD", dbase::FieldType::Integer),
            create_test_field_info("M_FIELD", dbase::FieldType::Logical),
        ];

        let schema = try_from_schema_with_mock(&fields, None).unwrap();
        assert_eq!(schema.len(), 3);

        // Check that order is preserved
        assert_eq!(schema.get_at_index(0).unwrap().0, "Z_FIELD");
        assert_eq!(schema.get_at_index(1).unwrap().0, "A_FIELD");
        assert_eq!(schema.get_at_index(2).unwrap().0, "M_FIELD");
    }

    #[test]
    fn test_schema_with_duplicate_field_names() {
        let fields = vec![
            create_test_field_info("NAME", dbase::FieldType::Character),
            create_test_field_info("NAME", dbase::FieldType::Integer),
        ];

        // Polars schemas don't allow duplicate field names - the second one overwrites the first
        let schema = try_from_schema_with_mock(&fields, None).unwrap();
        assert_eq!(schema.len(), 1); // Only one field remains due to duplicate name

        assert_eq!(schema.get_at_index(0).unwrap().0, "NAME");
        // The last field with the same name wins
        assert!(matches!(schema.get_at_index(0).unwrap().1, DataType::Int32));
    }

    #[test]
    fn test_data_type_parser_caching() {
        let fields = vec![
            create_test_field_info("FIELD1", dbase::FieldType::Character),
            create_test_field_info("FIELD2", dbase::FieldType::Character), // Same type
            create_test_field_info("FIELD3", dbase::FieldType::Integer),
            create_test_field_info("FIELD4", dbase::FieldType::Integer), // Same type
        ];

        let schema = try_from_schema_with_mock(&fields, None).unwrap();
        assert_eq!(schema.len(), 4);

        // All fields should be converted correctly
        assert!(matches!(
            schema.get_at_index(0).unwrap().1,
            DataType::String
        ));
        assert!(matches!(
            schema.get_at_index(1).unwrap().1,
            DataType::String
        ));
        assert!(matches!(schema.get_at_index(2).unwrap().1, DataType::Int32));
        assert!(matches!(schema.get_at_index(3).unwrap().1, DataType::Int32));
    }

    #[test]
    fn test_value_builders() {
        let mut string_builder = MutableBinaryViewArray::<str>::with_capacity(10);

        // Test character value
        let char_value = FieldValue::Character(Some("test".to_string()));
        assert!(string_builder.try_push_value(&char_value).is_ok());

        // Test null character value
        let null_value = FieldValue::Character(None);
        assert!(string_builder.try_push_value(&null_value).is_ok());

        // Test memo value
        let memo_value = FieldValue::Memo("memo content".to_string());
        assert!(string_builder.try_push_value(&memo_value).is_ok());

        // Test invalid type
        let int_value = FieldValue::Integer(42);
        assert!(string_builder.try_push_value(&int_value).is_err());
    }

    #[test]
    fn test_boolean_builder() {
        let mut bool_builder = MutableBooleanArray::with_capacity(10);

        let true_value = FieldValue::Logical(Some(true));
        assert!(bool_builder.try_push_value(&true_value).is_ok());

        let false_value = FieldValue::Logical(Some(false));
        assert!(bool_builder.try_push_value(&false_value).is_ok());

        let null_value = FieldValue::Logical(None);
        assert!(bool_builder.try_push_value(&null_value).is_ok());

        // Test invalid type
        let int_value = FieldValue::Integer(42);
        assert!(bool_builder.try_push_value(&int_value).is_err());
    }

    #[test]
    fn test_numeric_builders() {
        let mut int_builder = MutablePrimitiveArray::<i32>::with_capacity(10);
        let mut float_builder = MutablePrimitiveArray::<f64>::with_capacity(10);

        // Test integer
        let int_value = FieldValue::Integer(42);
        assert!(int_builder.try_push_value(&int_value).is_ok());

        // Test date in integer builder
        let date_value = FieldValue::Date(Some(dbase::Date::new(1, 1, 2023)));
        assert!(int_builder.try_push_value(&date_value).is_ok());

        // Test numeric in float builder
        let num_value = FieldValue::Numeric(Some(3.15));
        assert!(float_builder.try_push_value(&num_value).is_ok());

        // Test currency in float builder
        let currency_value = FieldValue::Currency(100.0);
        assert!(float_builder.try_push_value(&currency_value).is_ok());

        // Test double in float builder
        let double_value = FieldValue::Double(2.72);
        assert!(float_builder.try_push_value(&double_value).is_ok());
    }

    #[test]
    fn test_datetime_builder() {
        let mut datetime_builder = MutablePrimitiveArray::<i64>::with_capacity(10);

        let dt = dbase::DateTime::new(dbase::Date::new(1, 1, 2023), dbase::Time::new(12, 0, 0));
        let datetime_value = FieldValue::DateTime(dt);
        assert!(datetime_builder.try_push_value(&datetime_value).is_ok());

        // Test invalid type
        let int_value = FieldValue::Integer(42);
        assert!(datetime_builder.try_push_value(&int_value).is_err());
    }

    #[test]
    fn test_builder_factory() {
        let string_builder = new_value_builder(&DataType::String, 100);
        assert_eq!(string_builder.dtype(), &ArrowDataType::Utf8View);

        let bool_builder = new_value_builder(&DataType::Boolean, 100);
        assert_eq!(bool_builder.dtype(), &ArrowDataType::Boolean);

        let int_builder = new_value_builder(&DataType::Int32, 100);
        assert_eq!(int_builder.dtype(), &ArrowDataType::Int32);

        let float_builder = new_value_builder(&DataType::Float64, 100);
        assert_eq!(float_builder.dtype(), &ArrowDataType::Float64);
    }

    #[test]
    fn test_type_conversion() {
        assert_eq!(
            dbase_field_type_to_polars(&FieldType::Character).unwrap(),
            DataType::String
        );
        assert_eq!(
            dbase_field_type_to_polars(&FieldType::Logical).unwrap(),
            DataType::Boolean
        );
        assert_eq!(
            dbase_field_type_to_polars(&FieldType::Integer).unwrap(),
            DataType::Int32
        );
        assert_eq!(
            dbase_field_type_to_polars(&FieldType::Date).unwrap(),
            DataType::Date
        );
        assert_eq!(
            dbase_field_type_to_polars(&FieldType::DateTime).unwrap(),
            DataType::Datetime(TimeUnit::Milliseconds, Some(TimeZone::UTC))
        );
    }

    #[test]
    fn test_field_value_ext() {
        let char_value = FieldValue::Character(Some("test".to_string()));
        assert_eq!(char_value.field_type(), FieldType::Character);

        let int_value = FieldValue::Integer(42);
        assert_eq!(int_value.field_type(), FieldType::Integer);

        let bool_value = FieldValue::Logical(Some(true));
        assert_eq!(bool_value.field_type(), FieldType::Logical);
    }

    #[test]
    fn test_boxed_value_builder() {
        let mut builder: Box<dyn ValueBuilder> = Box::new(MutableBooleanArray::with_capacity(4));

        assert_eq!(builder.dtype(), &ArrowDataType::Boolean);
        assert_eq!(builder.len(), 0);
        assert!(builder.validity().is_none());

        builder.push_null();
        assert_eq!(builder.len(), 1);

        let true_value = FieldValue::Logical(Some(true));
        assert!(builder.try_push_value(&true_value).is_ok());
        assert_eq!(builder.len(), 2);
    }

    #[test]
    fn test_null_builder() {
        let mut builder = MutableNullArray::new(ArrowDataType::Null, 0);

        let any_value = FieldValue::Character(Some("test".to_string()));
        assert!(builder.try_push_value(&any_value).is_ok());
        assert_eq!(builder.len(), 1);
    }
}
