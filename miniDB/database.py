from __future__ import annotations
import pickle
from table import Table
from time import sleep, localtime, strftime
import os,sys
from btree import Btree
import shutil
from misc import split_condition
import logging
import warnings
import readline
from tabulate import tabulate


# sys.setrecursionlimit(100)

# Clear command cache (journal)
readline.clear_history()

class Database:
    '''
    Main Database class, containing tables.
    '''

    def __init__(self, name, load=True):
        self.tables = {}
        self._name = name

        self.savedir = f'dbdata/{name}_db'

        if load:
            try:
                self.load_database()
                logging.info(f'Loaded "{name}".')
                return
            except:
                warnings.warn(f'Database "{name}" does not exist. Creating new.')

        # create dbdata directory if it doesnt exist
        if not os.path.exists('dbdata'):
            os.mkdir('dbdata')

        # create new dbs save directory
        try:
            os.mkdir(self.savedir)
        except:
            pass

        # create all the meta tables
        self.create_table('meta_length', 'table_name,no_of_rows', 'str,int')
        self.create_table('meta_locks', 'table_name,pid,mode', 'str,int,str')
        self.create_table('meta_insert_stack', 'table_name,indexes', 'str,list')
        self.create_table('meta_indexes', 'table_name,index_name', 'str,str')

        # create a table that contains info about triggers of the current database
        self.create_table('triggers','trigger_name,trigger_table,action,when','str,str,str,str','trigger_name')
        
        self.save_database()

    def save_database(self):
        '''
        Save database as a pkl file. This method saves the database object, including all tables and attributes.
        '''
        for name, table in self.tables.items():
            with open(f'{self.savedir}/{name}.pkl', 'wb') as f:
                pickle.dump(table, f)

    def _save_locks(self):
        '''
        Stores the meta_locks table to file as meta_locks.pkl.
        '''
        with open(f'{self.savedir}/meta_locks.pkl', 'wb') as f:
            pickle.dump(self.tables['meta_locks'], f)

    def load_database(self):
        '''
        Load all tables that are part of the database (indices noted here are loaded).

        Args:
            path: string. Directory (path) of the database on the system.
        '''
        path = f'dbdata/{self._name}_db'
        for file in os.listdir(path):

            if file[-3:]!='pkl': # if used to load only pkl files
                continue
            f = open(path+'/'+file, 'rb')
            tmp_dict = pickle.load(f)
            f.close()
            name = f'{file.split(".")[0]}'
            self.tables.update({name: tmp_dict})
            # setattr(self, name, self.tables[name])

    #### TRIGGERS ####
    def create_trigger(self,trigger_name=None,table_name=None,when=None,action=None):
        
        '''
        This function is used to create a trigger which corresponds to a specific table of the database.
        The info of the new trigger is stored to the 'triggers' table of the Database
        
        Args:
            trigger_name: string. The name of the trigger.
            table_name: string. The table to whom trigger corresponds to.
            action: string. The action (INSERT,UPDATE,DELETE) after which the trigger will be fired.
            when: string. The time in which the trigger will be fired. Only two values are acceptable:
                BEFORE: trigger is fired before query is runs.
                AFTER: trigger is fired after query runs.
        '''
        
        self.load_database()
        
        # name of trigger can not be ""
        if trigger_name=='':
            print("Trigger's name can not be empty!")
            return

        '''
        check if action is INSERT, DELETE or UPDATE.
        If it's not, then return
        '''
        if action!='insert' and action!='delete' and action!='update':
            print('Action of trigger should be only INSERT or DELETE or UPDATE!')
            return

        
        # when clause can be only BEFORE or AFTER
        if when!='before' and when!='after':
            print('WHEN clause can be only BEFORE or AFTER')
            return


        # check if trigger to be created is on an existing table of the DB
        if table_name in self.tables.keys() and table_name!='triggers':
            # add a new row to 'triggers' table
            self.insert_into('triggers',trigger_name+','+table_name+','+action+','+when,True)
        else:
            print('You can not create a trigger on this table!')

    def drop_trigger(self,trigger_name=None):
        
        '''
        This function is used to delete an existing trigger from 'triggers' table
        
        Args:
            trigger_name: string. The name of the trigger to be deleted.
        '''
        
        self.load_database()

        # remove a row from 'triggers' table
        self.delete_from('triggers','trigger_name='+trigger_name,True)

    def check_for_triggers(self,trigger_table,action,when):

        '''
        This function scans the 'triggers' table from rows with specific values. This is because,
        in this project, every trigger executes the same function. In a database, there can exist
        many triggers on a specific table (ex. instructor) that are fired after a specific event
        (ex. update). So, in this method, it is counted how many times a trigger with the same action
        on the same table exists in the 'triggers' table

        Args:
            trigger_table: string. The name of the table that trigger corresponds to.
            action: string. The action of the trigger.
            when: string. Time, in which trigger is going to be fired.
        '''
        
        '''
        take the data of the second,third and fourth column of 
        'triggers' table and store them in the lists below
        '''
        list_tables = self.tables['triggers'].column_by_name('trigger_table')
        list_actions = self.tables['triggers'].column_by_name('action')
        list_when = self.tables['triggers'].column_by_name('when')

        counter = 0 

        # check if trigger exists with specific values (trigger_table, action and when)
        for x in range(len(list_tables)):
            if list_tables[x]==trigger_table and list_actions[x]==action and list_when[x]==when: 
                counter+=1 # if exist, then increase counter by 1
        
        return counter # return the number of times that a specific trigger exists

    
    def trigger_function(self,event,when):

        '''
        This function is excecuted after each trigger of the database
        is fired. The function shows a message to user.

        event: string. Is one of the following words: delete,update or insert
        when: Time in which trigger is fired. BEFORE or AFTER the query
        '''
        
        print("Trigger was executed "+when+" "+event+" query")

    #### IO ####

    def _update(self):
        '''
        Update all meta tables.
        '''
        self._update_meta_length()
        self._update_meta_insert_stack()


    def create_table(self, name, column_names, column_types, primary_key=None, load=None):
        '''
        This method create a new table. This table is saved and can be accessed via db_object.tables['table_name'] or db_object.table_name

        Args:
            name: string. Name of table.
            column_names: list. Names of columns.
            column_types: list. Types of columns.
            primary_key: string. The primary key (if it exists).
            load: boolean. Defines table object parameters as the name of the table and the column names.
        '''
        
        # print('here -> ', column_names.split(','))
        self.tables.update({name: Table(name=name, column_names=column_names.split(','), column_types=column_types.split(','), primary_key=primary_key, load=load)})
        # self._name = Table(name=name, column_names=column_names, column_types=column_types, load=load)
        # check that new dynamic var doesnt exist already
        # self.no_of_tables += 1
        self._update()
        self.save_database()
        # (self.tables[name])
        print(f'Created table "{name}".')


    def drop_table(self, table_name):
        '''
        Drop table from current database.

        Args:
            table_name: string. Name of table.
        '''

        # 'triggers' table can not be removed from the current Database
        if table_name=='triggers':
            print('You can not drop this table!')
            return

        self.load_database()
        self.lock_table(table_name)

        self.tables.pop(table_name)
        if os.path.isfile(f'{self.savedir}/{table_name}.pkl'):
            os.remove(f'{self.savedir}/{table_name}.pkl')
        else:
            warnings.warn(f'"{self.savedir}/{table_name}.pkl" not found.')
        self.delete_from('meta_locks', f'table_name={table_name}')
        self.delete_from('meta_length', f'table_name={table_name}')
        self.delete_from('meta_insert_stack', f'table_name={table_name}')

        # self._update()
        self.save_database()


    def import_table(self, table_name, filename, column_types=None, primary_key=None):
        '''
        Creates table from CSV file.

        Args:
            filename: string. CSV filename. If not specified, filename's name will be used.
            column_types: list. Types of columns. If not specified, all will be set to type str.
            primary_key: string. The primary key (if it exists).
        '''
        file = open(filename, 'r')

        first_line=True
        for line in file.readlines():
            if first_line:
                colnames = line.strip('\n')
                if column_types is None:
                    column_types = ",".join(['str' for _ in colnames.split(',')])
                self.create_table(name=table_name, column_names=colnames, column_types=column_types, primary_key=primary_key)
                lock_ownership = self.lock_table(table_name, mode='x')
                first_line = False
                continue
            self.tables[table_name]._insert(line.strip('\n').split(','))

        if lock_ownership:
             self.unlock_table(table_name)
        self._update()
        self.save_database()


    def export(self, table_name, filename=None):
        '''
        Transform table to CSV.

        Args:
            table_name: string. Name of table.
            filename: string. Output CSV filename.
        '''
        res = ''
        for row in [self.tables[table_name].column_names]+self.tables[table_name].data:
            res+=str(row)[1:-1].replace('\'', '').replace('"','').replace(' ','')+'\n'

        if filename is None:
            filename = f'{table_name}.csv'

        with open(filename, 'w') as file:
           file.write(res)

    def table_from_object(self, new_table):
        '''
        Add table object to database.

        Args:
            new_table: string. Name of new table.
        '''

        self.tables.update({new_table._name: new_table})
        if new_table._name not in self.__dir__():
            setattr(self, new_table._name, new_table)
        else:
            raise Exception(f'"{new_table._name}" attribute already exists in class "{self.__class__.__name__}".')
        self._update()
        self.save_database()



    ##### table functions #####

    # In every table function a load command is executed to fetch the most recent table.
    # In every table function, we first check whether the table is locked. Since we have implemented
    # only the X lock, if the tables is locked we always abort.
    # After every table function, we update and save. Update updates all the meta tables and save saves all
    # tables.

    # these function calls are named close to the ones in postgres

    def cast(self, column_name, table_name, cast_type):
        '''
        Modify the type of the specified column and cast all prexisting values.
        (Executes type() for every value in column and saves)

        Args:
            table_name: string. Name of table (must be part of database).
            column_name: string. The column that will be casted (must be part of database).
            cast_type: type. Cast type (do not encapsulate in quotes).
        '''
        self.load_database()
        
        lock_ownership = self.lock_table(table_name, mode='x')
        self.tables[table_name]._cast_column(column_name, eval(cast_type))
        if lock_ownership:
            self.unlock_table(table_name)
        self._update()
        self.save_database()

    def insert_into(self, table_name, row_str,flag=False):
        '''
        Inserts data to given table.

        Args:
            table_name: string. Name of table (must be part of database).
            row: list. A list of values to be inserted (will be casted to a predifined type automatically).
            lock_load_save: boolean. If False, user needs to load, lock and save the states of the database (CAUTION). Useful for bulk-loading.
            flag: Boolean. If false, then a insert query can not happen in 'triggers' table
                           If true,  then a insert query can happen in 'triggers' table 
        '''
        
        # check if a row can be inserted to table
        # Note: 'triggers' table can not be modified from a simple insert query
        if (table_name=='triggers' and flag) or table_name!='triggers':
            
            # check if exist BEFORE triggers with INSERT event
            k = self.check_for_triggers(table_name,'insert','before')

            # execute trigger's function
            for i in range(k):
                self.trigger_function('insert','before')
            
            # check if insert query changes the table. 
            # True: if the table is changed
            # False: otherwise
            # if the method throws exception, then insert query is failed and trigger_flag var is set as false
            trigger_flag = True 

            row = row_str.strip().split(',')
            self.load_database()
            # fetch the insert_stack. For more info on the insert_stack
            # check the insert_stack meta table
            lock_ownership = self.lock_table(table_name, mode='x')
            insert_stack = self._get_insert_stack_for_table(table_name)
            try:
                self.tables[table_name]._insert(row, insert_stack)
                print('Query is completed')
            except Exception as e:
                
                # insert query has not been successfuly completed. So if trigger after insert exists, it will not be fired!
                trigger_flag = False 
                
                logging.info(e)
                logging.info('ABORTED')
            
            self._update_meta_insert_stack_for_tb(table_name, insert_stack[:-1])

            if lock_ownership:
                self.unlock_table(table_name)
            self._update()
            self.save_database()

            if trigger_flag:
                # execute trigger if exists
                n = self.check_for_triggers(table_name,'insert','after')

                # execute trigger's function
                for i in range(n):
                    self.trigger_function('insert','after')
            
            return

        print('This table can not be modified!')


    def update_table(self, table_name, set_args, condition,flag=False):
        '''
        Update the value of a column where a condition is met.

        Args:
            table_name: string. Name of table (must be part of database).
            set_value: string. New value of the predifined column name.
            set_column: string. The column to be altered.
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
                
                Operatores supported: (<,<=,==,>=,>)
            
            flag: Boolean. If false, then a insert query can not happen in 'triggers' table
                           If true,  then a insert query can happen in 'triggers' table
        '''
        
        # check if a row can be updated in the table
        # Note: 'triggers' table can not be modified from a simple update query
        if (table_name=='triggers' and flag) or table_name!='triggers':

            # check if exist BEFORE triggers with UPDATE event
            k = self.check_for_triggers(table_name,'update','before')

            # execute trigger's function
            for i in range(k):
                self.trigger_function('update','before')

            set_column, set_value = set_args.replace(' ','').split('=')
            self.load_database()
            
            lock_ownership = self.lock_table(table_name, mode='x')
            changed = self.tables[table_name]._update_rows(set_value, set_column, condition)
            print('Query is completed')

            # if the query changed the table then check for triggers
            if changed:
                
                # execute trigger
                # stores the number of times that a specific trigger is being discovered
                n = self.check_for_triggers(table_name,'update','after')

                # execute trigger's function
                for i in range(n):
                    self.trigger_function('update','after')
                
            if lock_ownership:
                self.unlock_table(table_name)
            self._update()
            self.save_database()
            return
        
        print('This table can not be modified!')


    def delete_from(self, table_name, condition,flag=False):
        
        '''
        Delete rows of table where condition is met.

        Args:
            table_name: string. Name of table (must be part of database).
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
                
                Operatores supported: (<,<=,==,>=,>)
            
            flag: Boolean. If false, then a insert query can not happen in 'triggers' table
                           If true,  then a insert query can happen in 'triggers' table
        '''
        
        # check if a row can be deleted from table
        # Note: 'triggers' table can not be modified from a simple delete query
        if (table_name=='triggers' and flag) or table_name!='triggers':

            # check if exist BEFORE triggers with DELETE event
            k = self.check_for_triggers(table_name,'delete','before')

            # execute trigger's function
            for i in range(k):
                self.trigger_function('delete','before')
            
            self.load_database()
            
            lock_ownership = self.lock_table(table_name, mode='x')
            deleted = self.tables[table_name]._delete_where(condition)
            print('Query is completed')

            if lock_ownership:
                self.unlock_table(table_name)
            self._update()
            self.save_database()
            # we need the save above to avoid loading the old database that still contains the deleted elements
            if table_name[:4]!='meta':
                self._add_to_insert_stack(table_name, deleted)
            self.save_database()
            
            # if 'deleted' list is not empty, then scan for triggers
            if bool(deleted): 
                # execute triggers
                n = self.check_for_triggers(table_name,'delete','after')
                
                # execute trigger's function
                for i in range(n):
                    self.trigger_function('delete','after')

            return
        
        print('This table cannot be modified!')

    # added the distinct=False parameter
    def select(self, columns, table_name, condition, distinct=False, order_by=None, top_k=True,\
               desc=None, save_as=None, return_object=True):
        '''
        Selects and outputs a table's data where condtion is met.

        Args:
            table_name: string. Name of table (must be part of database).
            columns: list. The columns that will be part of the output table (use '*' to select all available columns)
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
                
                Operatores supported: (<,<=,==,>=,>)
            
            order_by: string. A column name that signals that the resulting table should be ordered based on it (no order if None).
            
            desc: boolean. If True, order_by will return results in descending order (True by default).
            
            distinct: If True, distinct will return results with non duplicate values. The distinct value is applied to the COMBINATION of the columns that are present in the query. 
                      If columns to be returned equals to "*", then distinct will not be applied.
                      If False, distinct will return results with duplicate values. False is the default value.
            
            top_k: int. An integer that defines the number of rows that will be returned (all rows if None).
            save_as: string. The name that will be used to save the resulting table into the database (no save if None).
            return_object: boolean. If True, the result will be a table object (useful for internal use - the result will be printed by default).
        '''
        
        '''
        if the word distinct is detected in the query, then remove it and set the distinct flag to True.
        That means that only non duplicate values can be shown in the column next to the word DISTINCT in the query.
        '''
        
        if 'distinct' in columns:
            columns = columns.replace('distinct ','')
            distinct = True

        # print(table_name)
        self.load_database()
        if isinstance(table_name,Table):
            return table_name._select_where(columns, condition, distinct, order_by, desc, top_k)

        if condition is not None:
            condition_column = split_condition(condition)[0]
        else:
            condition_column = ''

        
        # self.lock_table(table_name, mode='x')
        if self.is_locked(table_name):
            return
        if self._has_index(table_name) and condition_column==self.tables[table_name].column_names[self.tables[table_name].pk_idx]:
            index_name = self.select('*', 'meta_indexes', f'table_name={table_name}', return_object=True).column_by_name('index_name')[0]
            bt = self._load_idx(index_name)
            table = self.tables[table_name]._select_where_with_btree(columns, bt, condition, order_by, desc, top_k)
        else:
            table = self.tables[table_name]._select_where(columns, condition, distinct, order_by, desc, top_k)
        # self.unlock_table(table_name)
        if save_as is not None:
            table._name = save_as
            self.table_from_object(table)
        else:
            if return_object:
                return table
            else:
                return table.show()
        

    def show_table(self, table_name, no_of_rows=None):
        '''
        Print table in a readable tabular design (using tabulate).

        Args:
            table_name: string. Name of table (must be part of database).
        '''
        self.load_database()
        
        self.tables[table_name].show(no_of_rows, self.is_locked(table_name))


    def sort(self, table_name, column_name, asc=False):
        '''
        Sorts a table based on a column.

        Args:
            table_name: string. Name of table (must be part of database).
            column_name: string. the column name that will be used to sort.
            asc: If True sort will return results in ascending order (False by default).
        '''

        self.load_database()
        
        lock_ownership = self.lock_table(table_name, mode='x')
        self.tables[table_name]._sort(column_name, asc=asc)
        if lock_ownership:
            self.unlock_table(table_name)
        self._update()
        self.save_database()

    def join(self, mode, left_table, right_table, condition, save_as=None, return_object=True):
        '''
        Join two tables that are part of the database where condition is met.

        Args:
            left_table: string. Name of the left table (must be in DB) or Table obj.
            right_table: string. Name of the right table (must be in DB) or Table obj.
            condition: string. A condition using the following format:
                'column[<,<=,==,>=,>]value' or
                'value[<,<=,==,>=,>]column'.
                
                Operatores supported: (<,<=,==,>=,>)
        save_as: string. The output filename that will be used to save the resulting table in the database (won't save if None).
        return_object: boolean. If True, the result will be a table object (useful for internal usage - the result will be printed by default).
        '''
        self.load_database()
        if self.is_locked(left_table) or self.is_locked(right_table):
            return

        left_table = left_table if isinstance(left_table, Table) else self.tables[left_table] 
        right_table = right_table if isinstance(right_table, Table) else self.tables[right_table] 


        if mode=='inner':
            res = left_table._inner_join(right_table, condition)
        else:
            raise NotImplementedError

        if save_as is not None:
            res._name = save_as
            self.table_from_object(res)
        else:
            if return_object:
                return res
            else:
                res.show()

    def lock_table(self, table_name, mode='x'):
        '''
        Locks the specified table using the exclusive lock (X).

        Args:
            table_name: string. Table name (must be part of database).
        '''
        if table_name[:4]=='meta' or table_name not in self.tables.keys() or isinstance(table_name,Table):
            return

        with open(f'{self.savedir}/meta_locks.pkl', 'rb') as f:
            self.tables.update({'meta_locks': pickle.load(f)})

        try:
            pid = self.tables['meta_locks']._select_where('pid',f'table_name={table_name}').data[0][0]
            if pid!=os.getpid():
                raise Exception(f'Table "{table_name}" is locked by process with pid={pid}')
            else:
                return False

        except IndexError:
            pass

        if mode=='x':
            self.tables['meta_locks']._insert([table_name, os.getpid(), mode])
        else:
            raise NotImplementedError
        self._save_locks()
        return True
        # print(f'Locking table "{table_name}"')

    def unlock_table(self, table_name, force=False):
        '''
        Unlocks the specified table that is exclusively locked (X).

        Args:
            table_name: string. Table name (must be part of database).
        '''
        if table_name not in self.tables.keys():
            raise Exception(f'Table "{table_name}" is not in database')

        if not force:
            try:
                # pid = self.select('*','meta_locks',  f'table_name={table_name}', return_object=True).data[0][1]
                pid = self.tables['meta_locks']._select_where('pid',f'table_name={table_name}').data[0][0]
                if pid!=os.getpid():
                    raise Exception(f'Table "{table_name}" is locked by the process with pid={pid}')
            except IndexError:
                pass
        self.tables['meta_locks']._delete_where(f'table_name={table_name}')
        self._save_locks()
        # print(f'Unlocking table "{table_name}"')

    def is_locked(self, table_name):
        '''
        Check whether the specified table is exclusively locked (X).

        Args:
            table_name: string. Table name (must be part of database).
        '''
        if isinstance(table_name,Table) or table_name[:4]=='meta':  # meta tables will never be locked (they are internal)
            return False

        with open(f'{self.savedir}/meta_locks.pkl', 'rb') as f:
            self.tables.update({'meta_locks': pickle.load(f)})

        try:
            pid = self.tables['meta_locks']._select_where('pid',f'table_name={table_name}').data[0][0]
            if pid!=os.getpid():
                raise Exception(f'Table "{table_name}" is locked by the process with pid={pid}')

        except IndexError:
            pass
        return False

    def journal(idx = None):
        if idx != None:
            cache_list = '\n'.join([str(readline.get_history_item(i + 1)) for i in range(readline.get_current_history_length())]).split('\n')[int(idx)]
            out = tabulate({"Command": cache_list.split('\n')}, headers=["Command"])
        else:
            cache_list = '\n'.join([str(readline.get_history_item(i + 1)) for i in range(readline.get_current_history_length())])
            out = tabulate({"Command": cache_list.split('\n')}, headers=["Index","Command"], showindex="always")
        print('journal:', out)
        #return out


    #### META ####

    # The following functions are used to update, alter, load and save the meta tables.
    # Important: Meta tables contain info regarding the NON meta tables ONLY.
    # i.e. meta_length will not show the number of rows in meta_locks etc.

    def _update_meta_length(self):
        '''
        Updates the meta_length table.
        '''
        for table in self.tables.values():
            if table._name[:4]=='meta': #skip meta tables
                continue
            if table._name not in self.tables['meta_length'].column_by_name('table_name'): # if new table, add record with 0 no. of rows
                self.tables['meta_length']._insert([table._name, 0])

            # the result needs to represent the rows that contain data. Since we use an insert_stack
            # some rows are filled with Nones. We skip these rows.
            non_none_rows = len([row for row in table.data if any(row)])
            self.tables['meta_length']._update_rows(non_none_rows, 'no_of_rows', f'table_name={table._name}')
            # self.update_row('meta_length', len(table.data), 'no_of_rows', 'table_name', '==', table._name)

    def _update_meta_locks(self):
        '''
        Updates the meta_locks table.
        '''
        for table in self.tables.values():
            if table._name[:4]=='meta': #skip meta tables
                continue
            if table._name not in self.tables['meta_locks'].column_by_name('table_name'):

                self.tables['meta_locks']._insert([table._name, False])
                # self.insert('meta_locks', [table._name, False])

    def _update_meta_insert_stack(self):
        '''
        Updates the meta_insert_stack table.
        '''
        for table in self.tables.values():
            if table._name[:4]=='meta': #skip meta tables
                continue
            if table._name not in self.tables['meta_insert_stack'].column_by_name('table_name'):
                self.tables['meta_insert_stack']._insert([table._name, []])


    def _add_to_insert_stack(self, table_name, indexes):
        '''
        Adds provided indices to the insert stack of the specified table.

        Args:
            table_name: string. Table name (must be part of database).
            indexes: list. The list of indices that will be added to the insert stack (the indices of the newly deleted elements).
        '''
        old_lst = self._get_insert_stack_for_table(table_name)
        self._update_meta_insert_stack_for_tb(table_name, old_lst+indexes)

    def _get_insert_stack_for_table(self, table_name):
        '''
        Returns the insert stack of the specified table.

        Args:
            table_name: string. Table name (must be part of database).
        '''
        return self.tables['meta_insert_stack']._select_where('*', f'table_name={table_name}').column_by_name('indexes')[0]
        # res = self.select('meta_insert_stack', '*', f'table_name={table_name}', return_object=True).indexes[0]
        # return res

    def _update_meta_insert_stack_for_tb(self, table_name, new_stack):
        '''
        Replaces the insert stack of a table with the one supplied by the user.

        Args:
            table_name: string. Table name (must be part of database).
            new_stack: string. The stack that will be used to replace the existing one.
        '''
        self.tables['meta_insert_stack']._update_rows(new_stack, 'indexes', f'table_name={table_name}')


    # indexes
    def create_index(self, index_name, table_name, index_type='btree'):
        '''
        Creates an index on a specified table with a given name.
        Important: An index can only be created on a primary key (the user does not specify the column).

        Args:
            table_name: string. Table name (must be part of database).
            index_name: string. Name of the created index.
        '''
        if self.tables[table_name].pk_idx is None: # if no primary key, no index
            raise Exception('Cannot create index. Table has no primary key.')
        if index_name not in self.tables['meta_indexes'].column_by_name('index_name'):
            # currently only btree is supported. This can be changed by adding another if.
            if index_type=='btree':
                logging.info('Creating Btree index.')
                # insert a record with the name of the index and the table on which it's created to the meta_indexes table
                self.tables['meta_indexes']._insert([table_name, index_name])
                # crate the actual index
                self._construct_index(table_name, index_name)
                self.save_database()
        else:
            raise Exception('Cannot create index. Another index with the same name already exists.')

    def _construct_index(self, table_name, index_name):
        '''
        Construct a btree on a table and save.

        Args:
            table_name: string. Table name (must be part of database).
            index_name: string. Name of the created index.
        '''
        bt = Btree(3) # 3 is arbitrary

        # for each record in the primary key of the table, insert its value and index to the btree
        for idx, key in enumerate(self.tables[table_name].column_by_name(self.tables[table_name].pk)):
            bt.insert(key, idx)
        # save the btree
        self._save_index(index_name, bt)


    def _has_index(self, table_name):
        '''
        Check whether the specified table's primary key column is indexed.

        Args:
            table_name: string. Table name (must be part of database).
        '''
        return table_name in self.tables['meta_indexes'].column_by_name('table_name')

    def _save_index(self, index_name, index):
        '''
        Save the index object.

        Args:
            index_name: string. Name of the created index.
            index: obj. The actual index object (btree object).
        '''
        try:
            os.mkdir(f'{self.savedir}/indexes')
        except:
            pass

        with open(f'{self.savedir}/indexes/meta_{index_name}_index.pkl', 'wb') as f:
            pickle.dump(index, f)

    def _load_idx(self, index_name):
        '''
        Load and return the specified index.

        Args:
            index_name: string. Name of created index.
        '''
        f = open(f'{self.savedir}/indexes/meta_{index_name}_index.pkl', 'rb')
        index = pickle.load(f)
        f.close()
        return index
