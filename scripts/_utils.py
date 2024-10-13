import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

def load_and_preprocess_data(file_path):
    # Загрузка данных
    df = pd.read_csv(file_path)
    
    # Удаление лишних пробелов в названиях столбцов
    df.columns = df.columns.str.strip()
    
    # Преобразование временных меток в datetime
    time_columns = ['Время минимальной цены', 'Время минта', 'Время максимальной цены', 
                   'Время первой покупки']
    for col in time_columns:
        df[col] = pd.to_datetime(df[col], format="%H:%M:%S %d.%m.%Y")
    
    # Вычисление дополнительных метрик при необходимости
    return df

def exploratory_data_analysis(df):
    # Распределение начальной цены
    plt.figure(figsize=(10,6))
    sns.histplot(df['Цена в USD в начале'], bins=50, kde=True)
    plt.title('Распределение Начальной Цены Токенов')
    plt.xlabel('Цена в USD')
    plt.ylabel('Частота')
    plt.savefig('начальная_цена_распределение.png')  # Сохранение графика
    plt.close()
    
    # Временные зависимости
    plt.figure(figsize=(14,7))
    sns.lineplot(x='Время минимальной цены', y='Минимальная цена в USD', data=df)
    sns.lineplot(x='Время максимальной цены', y='Максимальная цена в USD', data=df)
    plt.title('Минимальная и Максимальная Цена во Времени')
    plt.xlabel('Время')
    plt.ylabel('Цена в USD')
    plt.legend(['Минимальная Цена', 'Максимальная Цена'])
    plt.savefig('временные_зависимости.png')  # Сохранение графика
    plt.close()
    
    # Корреляционная матрица только для числовых столбцов
    numeric_df = df.select_dtypes(include=['float64', 'int64'])
    plt.figure(figsize=(12,10))
    sns.heatmap(numeric_df.corr(), annot=True, fmt=".2f")
    plt.title('Корреляционная Матрица')
    plt.savefig('корреляционная_матрица.png')  # Сохранение графика
    plt.close()

def predict_max_price_time(df):
    # Выбор признаков
    features = ['Цена в USD в начале', 'Минимальная цена в USD', 
                'Разница в %']
    
    X = df[features]
    y = (df['Время максимальной цены'] - df['Время минта']).dt.total_seconds()
    
    # Разделение на обучающую и тестовую выборки
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Обучение модели
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    # Предсказание и оценка модели
    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)
    print(f'Mean Absolute Error: {mae} секунд')
    
    return model

def interpret_model(model, feature_names):
    importances = model.feature_importances_
    feature_importance = pd.Series(importances, index=feature_names).sort_values(ascending=False)
    
    plt.figure(figsize=(10,6))
    sns.barplot(x=feature_importance, y=feature_importance.index)
    plt.title('Важность Признаков')
    plt.xlabel('Важность')
    plt.ylabel('Признаки')
    plt.savefig('важность_признаков.png')  # Сохранение графика
    plt.close()

if __name__ == "__main__":
    df = load_and_preprocess_data('data.csv')
    exploratory_data_analysis(df)
    model = predict_max_price_time(df)
    interpret_model(model, ['Цена в USD в начале', 'Минимальная цена в USD', 'Разница в %'])