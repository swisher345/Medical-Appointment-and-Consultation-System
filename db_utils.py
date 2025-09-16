# db_utils.py


def get_object(model, **kwargs):
    """查询单个对象"""
    return model.query.filter_by(**kwargs).first()


def get_objects(model, **kwargs):
    """查询多个对象"""
    return model.query.filter_by(**kwargs).all()


def get_paginated_objects(model, page=1, per_page=10, **kwargs):
    """分页查询对象"""
    query = model.query.filter_by(**kwargs)
    return query.paginate(page=page, per_page=per_page, error_out=False)


def add_object(obj):
    """添加对象到数据库"""
    try:
        db.session.add(obj)
        db.session.commit()
        return True, obj
    except Exception as e:
        db.session.rollback()
        return False, str(e)


def update_object(obj, **kwargs):
    """更新对象属性"""
    for key, value in kwargs.items():
        setattr(obj, key, value)
    return add_object(obj)  # 复用添加对象的提交逻辑


def delete_object(obj):
    """从数据库中删除对象"""
    try:
        db.session.delete(obj)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        return False, str(e)
